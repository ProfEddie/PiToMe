export DATASET_PATH='/media/caduser/MyBook/chau/.cache'
export HF_DATASETS_CACHE='/media/caduser/MyBook/chau/.cache'
# for tasks in 'coco_cap' 'scienceqa_full' 'vqav2' 'flickr30k'
export model='llava-v1.5-7b'
for task in 'coco_cap' 
do 
    for ratio in '0.95' '0.925' '0.9'
    do 

        for algo in 'tome' 'pitome' 'tofu' 'diffrate'
        do 
            accelerate launch  --main_process_port 29501 --num_processes=6 -m lmms_eval \
                --model llava   \
                --model_args pretrained="liuhaotian/$model" \
                --tasks $task --log_samples \
                --log_samples_suffix $model_$task \
                --output_path ./logs/ \
                --batch_size 1 \
                --algo tome \
                --ratio 0.95 \
                --wandb_args project=$model-$task,name=$algo-$ratio
        done
    done
done

