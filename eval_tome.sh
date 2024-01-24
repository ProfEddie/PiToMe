
# export CKT_SIZE='vit_base_patch16_mae'
export CKT_SIZE='vit_large_patch16_mae'
# export CKT_SIZE='vit_huge_patch14_mae'

# export CKT_SIZE='deit_tiny_patch16_224'
# export CKT_SIZE='deit_small_patch16_224'
# export CKT_SIZE='deit_base_patch16_224'

# export CKT_SIZE='vit_small_patch16_224'
# export CKT_SIZE='vit_base_patch16_224'
# export CKT_SIZE='vit_large_patch16_224'

python ic/main_tome.py --eval --load_compression_rate --data-path $path_to_imagenet$ --model ${CKT_SIZE}  --r 8 --ratio  0.9385 
