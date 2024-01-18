export CKT_PATH='/mnt/data/mount_4TBSSD/nmduy/mae_ckts'

export CKT_SIZE='huge'
export PATCH='14'
export ALGO=$1
export R='8'
export RATIO='0.95'

python mae/main_finetune.py --eval --resume ${CKT_PATH}/mae_finetuned_vit_${CKT_SIZE}.pth --model vit_${CKT_SIZE}_patch${PATCH} --batch_size 100 --ratio ${RATIO} --compress_method ${ALGO}  --r ${R}
