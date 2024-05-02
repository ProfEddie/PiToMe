from transformers.models.clip.modeling_clip import CLIPEncoder
from transformers.modeling_outputs import BaseModelOutput
from typing import Optional, Tuple, Union
import torch
from ..merge import merge_source,  bipartite_soft_matching 


class ToFuCLIPEncoder(CLIPEncoder):
    """
    Transformer encoder consisting of `config.num_hidden_layers` self attention layers. Each layer is a
    [`CLIPEncoderLayer`].

    Args:
        config: CLIPConfig
    """

    def init_strategy(self, strategies):
        # self.margin = nn.Parameter(torch.tensor(margin)) 
        self.strategies = strategies 



    def compress_x(self, metric, x, attn, idx):
        ratio = self._tofu_info["ratio"].pop()
        if ratio < 1.0:
            merge, _ = bipartite_soft_matching(
                ratio=ratio,
                metric=metric,
                class_token=self._tofu_info["class_token"]
            )

            if self._tofu_info["trace_source"]:
                self._tofu_info["source"] = merge_source(
                    merge, x, self._tofu_info["source"]
                )
            x = merge(x, mode=self.strategies[idx])
        return x



    def forward(
        self,
        inputs_embeds,
        attention_mask: Optional[torch.Tensor] = None,
        causal_attention_mask: Optional[torch.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple, BaseModelOutput]:
        r"""
        Args:
            inputs_embeds (`torch.FloatTensor` of shape `(batch_size, sequence_length, hidden_size)`):
                Optionally, instead of passing `input_ids` you can choose to directly pass an embedded representation.
                This is useful if you want more control over how to convert `input_ids` indices into associated vectors
                than the model's internal embedding lookup matrix.
            attention_mask (`torch.Tensor` of shape `(batch_size, sequence_length)`, *optional*):
                Mask to avoid performing attention on padding token indices. Mask values selected in `[0, 1]`:

                - 1 for tokens that are **not masked**,
                - 0 for tokens that are **masked**.

                [What are attention masks?](../glossary#attention-mask)
            causal_attention_mask (`torch.Tensor` of shape `(batch_size, sequence_length)`, *optional*):
                Causal mask for the text model. Mask values selected in `[0, 1]`:

                - 1 for tokens that are **not masked**,
                - 0 for tokens that are **masked**.

                [What are attention masks?](../glossary#attention-mask)
            output_attentions (`bool`, *optional*):
                Whether or not to return the attentions tensors of all attention layers. See `attentions` under
                returned tensors for more detail.
            output_hidden_states (`bool`, *optional*):
                Whether or not to return the hidden states of all layers. See `hidden_states` under returned tensors
                for more detail.
            return_dict (`bool`, *optional*):
                Whether or not to return a [`~utils.ModelOutput`] instead of a plain tuple.
        """
    
        self._tofu_info["r"] = [self.r]* len(self.layers) 
        # self._tofu_info["ratio"] = [self.ratio] * len(self.layers) 
        self._tofu_info["ratio"] = [self.ratio if i%2==0  else 1.0 for i in range(len(self.layers)) ]
        self._tofu_info["size"] = None
        self._tofu_info["source"] = None
        output_attentions = output_attentions if output_attentions is not None else self.config.output_attentions
        output_hidden_states = (
            output_hidden_states if output_hidden_states is not None else self.config.output_hidden_states
        )
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        encoder_states = () if output_hidden_states else None
        all_attentions = () if output_attentions else None
        self.total_flops = 0

        hidden_states = inputs_embeds
        for idx, encoder_layer in enumerate(self.layers):
            if output_hidden_states:
                encoder_states = encoder_states + (hidden_states,)
            if self.gradient_checkpointing and self.training:
                layer_outputs = self._gradient_checkpointing_func(
                    encoder_layer.__call__,
                    hidden_states,
                    attention_mask,
                    causal_attention_mask,
                    output_attentions=True,
                )
            else:
                layer_outputs = encoder_layer(
                    hidden_states,
                    attention_mask,
                    causal_attention_mask,
                    output_attentions=True,
                )

            hidden_states = layer_outputs[0]
            self.total_flops += self.calculate_block_flop(hidden_states.shape)
            hidden_states = self.compress_x(hidden_states, hidden_states, layer_outputs[1], idx)

            if output_attentions:
                all_attentions = all_attentions + (layer_outputs[1],)
        # print('current flop:', self.total_flops/1e9)

        if output_hidden_states:
            encoder_states = encoder_states + (hidden_states,)

        if not return_dict:
            return tuple(v for v in [hidden_states, encoder_states, all_attentions] if v is not None)
        return BaseModelOutput(
            last_hidden_state=hidden_states, hidden_states=encoder_states, attentions=all_attentions
        )


    def calculate_block_flop(self, shape):
            flops = 0
            _,N, C = shape
            mhsa_flops = 4*N*C*C + 2*N*N*C
            flops += mhsa_flops
            ffn_flops = 8*N*C*C
            flops += ffn_flops
            return flops


def apply_patch(
   model: CLIPEncoder, trace_source: bool = False, prop_attn: bool = True, margin=0.9, use_k=False, output_attn=False):
    """
    Applies ToFu to this transformer. Afterward, set r using model.r.

    If you want to know the source of each token (e.g., for visualization), set trace_source = true.
    The sources will be available at model._tofu_info["source"] afterward.

    For proportional attention, set prop_attn to True. This is only necessary when evaluating models off
    the shelf. For trianing and for evaluating MAE models off the self set this to be False.
    """
    print('using', 'tofu')

    model.__class__ =  ToFuCLIPEncoder 
    model.ratio = 1.0 
    model.r=0.0
    num_layers = len(model.layers)
    
    strategies = ['tofu' if i > num_layers//2 else 'prune' for i in range(num_layers)]
    model.init_strategy(strategies)
    # model.compress_method = 'tofu' 
    model._tofu_info = {
        "ratio": model.ratio,
        "margin":  [],
        "size": None,
        "source": None,
        "output_attn": output_attn,
        "trace_source": trace_source,
        "prop_attn": prop_attn,
        "class_token": True,
        "distill_token": False,
    }
    current_layer = 0
    margin = margin 