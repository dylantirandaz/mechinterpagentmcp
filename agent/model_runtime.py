from __future__ import annotations

import os

os.environ.setdefault("HF_DEACTIVATE_ASYNC_LOAD", "1")
from dataclasses import dataclass

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = os.environ.get("AGENT_MODEL_ID", "Qwen/Qwen2.5-3B-Instruct")
MAX_NEW_TOKENS = 256


@dataclass
class GenerationResult:
    text: str
    prompt_token_count: int


class AgentModel:
    def __init__(self, model_id: str = MODEL_ID, attn_implementation: str | None = None) -> None:
        self.model_id = model_id
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        import transformers

        dtype_kw = "dtype" if int(transformers.__version__.split(".")[0]) >= 5 else "torch_dtype"
        kwargs = {"device_map": self.device, dtype_kw: dtype}
        if attn_implementation:
            kwargs["attn_implementation"] = attn_implementation
        self.model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
        self.model.eval()
        self._knockout_handles: list = []

    @property
    def num_layers(self) -> int:
        return self.model.config.num_hidden_layers

    @property
    def hidden_size(self) -> int:
        return self.model.config.hidden_size

    @property
    def num_attention_heads(self) -> int:
        return self.model.config.num_attention_heads

    @property
    def head_dim(self) -> int:
        return getattr(self.model.config, "head_dim", self.hidden_size // self.num_attention_heads)

    def render(
        self, messages: list[dict], tools: list[dict] | None, add_generation_prompt: bool
    ) -> torch.Tensor:
        return self._render(messages, tools, add_generation_prompt)

    def _render(
        self, messages: list[dict], tools: list[dict] | None, add_generation_prompt: bool
    ) -> torch.Tensor:
        ids = self.tokenizer.apply_chat_template(
            messages, tools=tools, add_generation_prompt=add_generation_prompt, return_tensors="pt"
        )
        return ids.to(self.device)

    @torch.no_grad()
    def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_new_tokens: int = MAX_NEW_TOKENS,
    ) -> GenerationResult:
        input_ids = self._render(messages, tools, add_generation_prompt=True)
        attention_mask = torch.ones_like(input_ids)
        out = self.model.generate(
            input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=None,
            top_p=None,
            top_k=None,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        new_tokens = out[0, input_ids.shape[1] :]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        return GenerationResult(text=text.strip(), prompt_token_count=int(input_ids.shape[1]))

    def install_direction_ablation(
        self,
        hidden_state_index: int,
        d_unit: np.ndarray,
        target_proj: float,
        prefill_only: bool = False,
    ) -> None:
        if hidden_state_index < 1:
            raise ValueError("can only ablate after a decoder layer (index >= 1)")
        layer_mod = self.model.model.layers[hidden_state_index - 1]
        direction = torch.tensor(d_unit, dtype=self.model.dtype, device=self.device)

        def hook(_module, _inp, out):
            hs = out[0] if isinstance(out, tuple) else out
            if prefill_only and hs.shape[1] == 1:
                return out
            proj = (hs * direction).sum(dim=-1, keepdim=True)
            hs2 = hs - (proj - target_proj) * direction
            return (hs2, *out[1:]) if isinstance(out, tuple) else hs2

        self.clear_ablation()
        self._ablation_handle = layer_mod.register_forward_hook(hook)

    def clear_ablation(self) -> None:
        handle = getattr(self, "_ablation_handle", None)
        if handle is not None:
            handle.remove()
            self._ablation_handle = None

    @torch.no_grad()
    def residual_at_decision(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> np.ndarray:
        input_ids = self._render(messages, tools, add_generation_prompt=False)
        out = self.model(
            input_ids, attention_mask=torch.ones_like(input_ids), output_hidden_states=True
        )
        last_idx = input_ids.shape[1] - 1
        stack = torch.stack([h[0, last_idx, :] for h in out.hidden_states], dim=0)
        return stack.float().cpu().numpy()

    @torch.no_grad()
    def logit_lens_last(
        self, messages: list[dict], tools: list[dict] | None, target_token_ids: dict[str, int]
    ) -> dict:
        input_ids = self._render(messages, tools, add_generation_prompt=True)
        out = self.model(
            input_ids, attention_mask=torch.ones_like(input_ids), output_hidden_states=True
        )
        norm = self.model.model.norm
        w_u = self.model.lm_head.weight
        last = input_ids.shape[1] - 1
        per_layer = {name: [] for name in target_token_ids}
        argmax_tok = []
        for h in out.hidden_states:
            resid = h[0, last, :]
            logits = torch.matmul(norm(resid), w_u.T)
            argmax_tok.append(int(logits.argmax()))
            for name, tid in target_token_ids.items():
                per_layer[name].append(round(float(logits[tid]), 3))
        return {
            "per_layer_logit": per_layer,
            "argmax_token_per_layer": argmax_tok,
            "final_argmax": self.tokenizer.decode([argmax_tok[-1]]),
        }

    @torch.no_grad()
    def attention_from_last_to_span(
        self, messages: list[dict], tools: list[dict] | None, span: tuple[int, int]
    ) -> np.ndarray:
        input_ids = self._render(messages, tools, add_generation_prompt=True)
        out = self.model(
            input_ids, attention_mask=torch.ones_like(input_ids), output_attentions=True
        )
        if out.attentions is None or out.attentions[0] is None:
            raise RuntimeError("no attention weights — load with attn_implementation='eager'")
        last = input_ids.shape[1] - 1
        start, end = span
        result = np.zeros((self.num_layers, self.num_attention_heads))
        for layer, attn in enumerate(out.attentions):
            from_last = attn[0, :, last, :]
            result[layer] = from_last[:, start:end].sum(dim=-1).float().cpu().numpy()
        return result

    def install_head_knockout(self, specs: list[tuple[int, int]]) -> None:
        self.clear_head_knockout()
        hd = self.head_dim
        by_layer: dict[int, list[int]] = {}
        for layer, head in specs:
            by_layer.setdefault(layer, []).append(head)

        def make_pre_hook(heads: list[int]):

            def pre_hook(_module, args):
                x = args[0].clone()
                for head in heads:
                    x[..., head * hd : (head + 1) * hd] = 0
                return (x, *args[1:])

            return pre_hook

        for layer, heads in by_layer.items():
            o_proj = self.model.model.layers[layer].self_attn.o_proj
            self._knockout_handles.append(o_proj.register_forward_pre_hook(make_pre_hook(heads)))

    def clear_head_knockout(self) -> None:
        for handle in self._knockout_handles:
            handle.remove()
        self._knockout_handles = []

    def install_position_ablation(self, positions: list[int]) -> None:
        self.clear_position_ablation()
        self._pos_handles: list = []
        pos = list(positions)

        def make_hook():

            def hook(_module, _inp, out):
                hs = out[0] if isinstance(out, tuple) else out
                if hs.shape[1] <= 1:
                    return out
                hs = hs.clone()
                hs[:, pos, :] = 0
                return (hs, *out[1:]) if isinstance(out, tuple) else hs

            return hook

        for layer in self.model.model.layers:
            self._pos_handles.append(layer.register_forward_hook(make_hook()))

    def clear_position_ablation(self) -> None:
        for handle in getattr(self, "_pos_handles", []):
            handle.remove()
        self._pos_handles = []
