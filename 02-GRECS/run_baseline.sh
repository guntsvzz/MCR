
echo "------------- 1 : Process the files for Recbole -------------"
# Process the processed files for RecBole (after processing the original files for Graph Reasoning) 
python3 src/baselines/format_beauty.py \
    --config config/beauty/baselines/format.json
# After this process, all the files from beauty have been standardized into the format needed by RecBole. 
# We follow the same process for the other datasets:  
echo "-------------- Formatting CDs --------------------------"
python3 src/baselines/format_cds.py \
    --config config/cds/baselines/format.json
echo "-------------- Formatting Cellphones -------------------"
python3 src/baselines/format_cellphones.py \
    --config config/cellphones/baselines/format.json
echo "-------------- Formatting Clothing ---------------------"
python3 src/baselines/format_clothing.py \
    --config config/clothing/baselines/format.json
echo "--------------------------------------------------------"
# python3 src/baselines/format_coco.py \
#     --config config/coco/baselines/format.json

echo "------------- 2 : Run the baselines -------------"
# To run a baseline on Beauty, choose a yaml config file in config/beauty/baselines and run the following:
DATASET_NAMES=("beauty" "cds" "cellphones" "clothing")

# DATASET_NAME=beauty
for DATASET_NAME in "${DATASET_NAMES[@]}"; do
    python3 src/baselines/baseline.py \
        --config config/${DATASET_NAME}/baselines/BPR.yaml
    python3 src/baselines/baseline.py \
        --config config/${DATASET_NAME}/baselines/CFKG.yaml
    python3 src/baselines/baseline.py \
        --config config/${DATASET_NAME}/baselines/ItemKNN.yaml
    python3 src/baselines/baseline.py \
        --config config/${DATASET_NAME}/baselines/KGCN.yaml
    python3 src/baselines/baseline.py \
        --config config/${DATASET_NAME}/baselines/MKR.yaml
    python3 src/baselines/baseline.py \
        --config config/${DATASET_NAME}/baselines/NeuMF.yaml
    python3 src/baselines/baseline.py \
        --config config/${DATASET_NAME}/baselines/Pop.yaml
    python3 src/baselines/baseline.py \
        --config config/${DATASET_NAME}/baselines/SpectralCF.yaml
done
# This example runs the Pop baseline on the Beauty dataset.
# You can ignore the warning "command line args [--config config/baselines/Pop.yaml] will not be used in RecBole". The argument is used properly.