# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.

# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
# --------------------------------------------------------

import math
from typing import Callable, Tuple
import torch
import torch.nn.functional as F


def do_nothing(x, mode=None):
    return x

def get_bsm_merge(
    node_max:torch.Tensor,
    node_idx:torch.Tensor,
    r:int,
    class_token=False
) -> Tuple[Callable, Callable]:

    edge_idx = node_max.argsort(dim=-1, descending=True)[..., None]
    unm_idx = edge_idx[..., r:, :]  # Unmerged Tokens
    src_idx = edge_idx[..., :r, :]  # Merged Tokens
    dst_idx = node_idx[..., None].gather(dim=-2, index=src_idx)
    def merge(x: torch.Tensor, mode="mean") -> torch.Tensor:
        if class_token:
            x_cls=x[:,0,:].unsqueeze(1)
            x=x[:,1:,:]
        else:
            x_cls = None
        # x = x[batch_idx, std_idx, :] 
        src, dst = x[..., ::2, :], x[..., 1::2, :]
        n, t1, c = src.shape
        unm = src.gather(dim=-2, index=unm_idx.expand(n, t1 - r, c))
        src = src.gather(dim=-2, index=src_idx.expand(n, r, c))
        dst = dst.scatter_reduce(-2, dst_idx.expand(n, r, c), src, reduce=mode)

        if x_cls is not None:
            return torch.cat([x_cls, unm, dst], dim=1)
        else:
            return torch.cat([unm, dst], dim=1)

    return merge, None



def pitome(
    x: torch.Tensor, 
    r:int=0,
    ratio:float=1.0,
    margin:float=0.5,
    class_token: bool = False,
):

    with torch.no_grad():
        if class_token:
            x=x[:,1:,:]
        B,T,_ = x.shape
        if r > 0:
            r = min(r, T // 2)
        elif ratio < 1.0:
            r = math.floor(T- T*ratio)
        else:
            return do_nothing, do_nothing

        x = F.normalize(x, p=2, dim=-1) 

        if margin >=0.45:
            a, b = x[..., ::2, :], x[..., 1::2, :]
            scores = a @ b.transpose(-1, -2)
            node_max, node_idx = scores.max(dim=-1)
            return get_bsm_merge(node_max, node_idx, r, class_token)

        batch_idx = torch.arange(B).unsqueeze_(1).to(x.device)
        sim =x@x.transpose(-1,-2) 
        sim  = torch.where(sim > margin, sim, -margin)
        isolation_score = sim.mean(dim=-2)
        indices =  torch.argsort(isolation_score, descending=True)
        min_indices = indices[..., :2*r]
        protected_idx = indices[..., 2*r:]
        a_idx, b_idx = min_indices[..., ::2], min_indices[..., 1::2]
        a, b = x[batch_idx, a_idx, :], x[batch_idx,  b_idx, :]
        scores = a@b.transpose(-1,-2) 
        _, dst_idx = scores.max(dim=-1) 
    
    def merge(x: torch.Tensor, mode="mean") -> torch.Tensor:
        if class_token:
            x_cls=x[:,0,:].unsqueeze(1)
            x=x[:,1:,:]
        else:
            x_cls = None
        B, _, C = x.shape

        protected = x[batch_idx, protected_idx,:] 
        src, dst = x[batch_idx, a_idx, :], x[batch_idx, b_idx, :]

        dst = dst.scatter_reduce(-2, dst_idx.unsqueeze(2).expand(B, r, C), src, reduce=mode)
        if x_cls is not None:
            return torch.cat([x_cls, protected, dst], dim=1)
        else:
            return torch.cat([protected, dst], dim=1)

    return merge, isolation_score

def merge_mean(
    merge: Callable, x: torch.Tensor
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Applies the merge function by taking a average based on token size.
    Returns the merged tensor and the new token sizes.
    """
    x = merge(x, mode="mean")
    return x




def merge_source(
    merge: Callable, x: torch.Tensor, source: torch.Tensor = None
) -> torch.Tensor:
    """
    For source tracking. Source is an adjacency matrix between the initial tokens and final merged groups.
    x is used to find out how many tokens there are in case the source is None.
    """
    if source is None:
        n, t, _ = x.shape
        source = torch.eye(t, device=x.device)[None, ...].expand(n, t, t)

    source = merge(source, mode="amax")
    return source
