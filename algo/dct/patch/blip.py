import torch
from lavis.models.vit import VisionTransformer,  Block
from ..merge import dc_transform 

class DCTBlock(Block):
    """
    Modifications:
     - Apply DCT between the attention and mlp blocks
     - Compute and propogate token size and potentially the token sources.
    """
    
    def compress_x(self, metric, x):
        ratio = self._dct_info["ratio"].pop()
        if ratio < 1.0:
            x = dc_transform(
                x, 
                ratio=ratio, 
                class_token=self._dct_info["class_token"]
            )

        return x

    def forward(self, x, register_hook=False):
        # attn_size = self._dct_info["size"] if self._dct_info["prop_attn"] else None
        # x_attn, metric, attn = self.attn(self.norm1(x), register_hook=register_hook)
        # x = x + self.drop_path(x_attn)
        # x = self.compress_x(metric, x) 
        # x = x + self.drop_path(self.mlp(self.norm2(x)))
        # return x
        x = x + self.drop_path(self.attn(self.norm1(x), register_hook=register_hook))
        x = x + self.drop_path(self.mlp(self.norm2(x)))
        x = self.compress_x(x, x) 
        # print(x.shape)
        return x




def make_dct_class(transformer_class):
    class DCTVisionTransformer(transformer_class):
        """
        Modifications:
        - Initialize r, token size, and token sources.
        """

        def forward(self,x, register_blk=-1):
            self._dct_info["r"] = [self.r]* len(self.blocks) 
            self._dct_info["ratio"] = [self.ratio] * len(self.blocks) 
            self._dct_info["size"] = None
            self._dct_info["source"] = None
            self.total_flop = 0
            self.final_shape = 0
            B = x.shape[0]
            x = self.patch_embed(x)

            cls_tokens = self.cls_token.expand(
                B, -1, -1
            )  # stole cls_tokens impl from Phil Wang, thanks
            x = torch.cat((cls_tokens, x), dim=1)

            x = x + self.pos_embed[:, : x.size(1), :]
            x = self.pos_drop(x)

            for i, blk in enumerate(self.blocks):
                self.total_flop += self.calculate_block_flop(x.shape)
                x = blk(x, register_blk == i)
            x = self.norm(x)
            self.final_flop=x.shape
            return x


        def forward_features(self, x, register_blk=-1) -> torch.Tensor:
      
            self._dct_info["r"] = [self.r]* len(self.blocks) 
            self._dct_info["ratio"] = [self.ratio] * len(self.blocks) 
            self._dct_info["size"] = None
            self._dct_info["source"] = None
            self.total_flop = 0

            B = x.shape[0]
            x = self.patch_embed(x)

            cls_tokens = self.cls_token.expand(
                B, -1, -1
            )  # stole cls_tokens impl from Phil Wang, thanks
            x = torch.cat((cls_tokens, x), dim=1)

            x = x + self.pos_embed[:, : x.size(1), :]
            x = self.pos_drop(x)

            for i, blk in enumerate(self.blocks):
                self.total_flop += self.calculate_block_flop(x.shape)
                x = blk(x, register_blk == i)
            x = self.norm(x)
            self.final_shape = x.shape
            return x


        def calculate_block_flop(self, shape):
            flops = 0
            _, N, C = shape
            mhsa_flops = 4*N*C*C + 2*N*N*C
            flops += mhsa_flops
            ffn_flops = 8*N*C*C
            flops += ffn_flops
            return flops

    return DCTVisionTransformer


def apply_patch(
   model: VisionTransformer, trace_source: bool = False, prop_attn: bool = True, margin=0.9, use_k=False):
    """
    Applies DCT to this transformer. Afterward, set r using model.r.

    If you want to know the source of each token (e.g., for visualization), set trace_source = true.
    The sources will be available at model._dct_info["source"] afterward.

    For proportional attention, set prop_attn to True. This is only necessary when evaluating models off
    the shelf. For trianing and for evaluating MAE models off the self set this to be False.
    """
    DCTVisionTransformer = make_dct_class(model.__class__)
    print('using', 'dct')

    model.__class__ = DCTVisionTransformer
    model.ratio = 1.0 
    model.r=0.0
    
    # model.compress_method = 'dct' 
    model._dct_info = {
        "ratio": model.ratio,
        "margin":  [],
        "size": None,
        "source": None,
        "trace_source": trace_source,
        "prop_attn": prop_attn,
        "class_token": model.cls_token is not None,
        "distill_token": False,
    }
    current_layer = 0
    margin = margin 
    num_layers = len(model.blocks)
    # margins = [margin - margin*(i/num_layers) for i in range(num_layers)]

    if hasattr(model, "dist_token") and model.dist_token is not None:
        model._dct_info["distill_token"] = True

    for module in model.modules():
        if isinstance(module, Block):
            # module.__class__ = DCTBlock if compress_method == 'dct' else PiDCTBlock 
            module.__class__ = DCTBlock
            module._dct_info = model._dct_info
            current_layer +=1
