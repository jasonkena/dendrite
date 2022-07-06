#!/bin/tcsh -e
#SBATCH --job-name=generate-pipeline # Job name
#SBATCH --array=1-10 # inclusive range
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task 48 # 1 cpu on single node
#SBATCH --mem=30gb # Job memory request
#SBATCH --time=120:00:00 # Time limit hrs:min:sec
#SBATCH --mail-type=BEGIN,END,FAIL. # Mail events (NONE, BEGIN, END, FAIL, ALL)
#SBATCH --mail-user=adhinart@bc.edu # Where to send mail
#SBATCH --partition=partial_nodes,full_nodes48,full_nodes64,gpuv100,gpua100

# assumes that raw.h5, spine.h5, bbox.npy exists
# entire pipeline for generating files base h5 up to the final segmentation + point generation
# merge has to be run manually
module purge
module load anaconda
conda activate dendrite

setenv BASE_PATH mouse
setenv TMPDIR /scratch/adhinart/dendrite/$SLURM_ARRAY_TASK_ID/$BASE_PATH

rm -rf $TMPDIR
mkdir -p $TMPDIR

cd /mmfs1/data/adhinart/dendrite/$BASE_PATH
mkdir -p extracted
# for points
mkdir -p results
mkdir -p pred
mkdir -p inference
mkdir -p baseline

cp *.h5 $TMPDIR
cp *.npy $TMPDIR

cd ..

# extraction for raw.h5
if ( -f "$BASE_PATH/extracted/$SLURM_ARRAY_TASK_ID.h5" ) then
    echo Extraction already exists
    cp $BASE_PATH/extracted/$SLURM_ARRAY_TASK_ID.h5 $TMPDIR
else
    python3 extract_seg.py $TMPDIR $SLURM_ARRAY_TASK_ID raw
    cp $TMPDIR/$SLURM_ARRAY_TASK_ID.h5 $BASE_PATH/extracted/
endif
echo extract_seg finished

# extraction for raw_gt.h5
if ( -f "$BASE_PATH/extracted/gt_$SLURM_ARRAY_TASK_ID.h5" ) then
    echo GT Extraction already exists
    cp $BASE_PATH/extracted/gt_$SLURM_ARRAY_TASK_ID.h5 $TMPDIR
else
    python3 extract_seg.py $TMPDIR $SLURM_ARRAY_TASK_ID raw_gt
    cp $TMPDIR/gt_$SLURM_ARRAY_TASK_ID.h5 $BASE_PATH/extracted/
endif
echo gt_extract_seg finished

if ( -f "$BASE_PATH/results/sparse_$SLURM_ARRAY_TASK_ID.npy" && -f "$BASE_PATH/results/dense_$SLURM_ARRAY_TASK_ID.npy" ) then
    echo Points already exist
    cp $BASE_PATH/results/sparse_$SLURM_ARRAY_TASK_ID.npy $TMPDIR
    cp $BASE_PATH/results/dense_$SLURM_ARRAY_TASK_ID.npy $TMPDIR
else
    python3 point.py $TMPDIR $SLURM_ARRAY_TASK_ID
    cp $TMPDIR/sparse_$SLURM_ARRAY_TASK_ID.npy $BASE_PATH/results/
    cp $TMPDIR/dense_$SLURM_ARRAY_TASK_ID.npy $BASE_PATH/results/
endif
echo point_generation finished

# NOTE: implement prediction
echo Skipping prediction step, assuming pred path exists
cp $BASE_PATH/pred/$SLURM_ARRAY_TASK_ID.npz $TMPDIR

if ( -f "$BASE_PATH/inference/inferred_$SLURM_ARRAY_TASK_ID.h5" ) then
    echo Inference already exists
    cp $BASE_PATH/inference/inferred_$SLURM_ARRAY_TASK_ID.h5 $TMPDIR
else
    python3 inference.py $TMPDIR $SLURM_ARRAY_TASK_ID
    cp $TMPDIR/inferred_$SLURM_ARRAY_TASK_ID.h5 $BASE_PATH/inference/
endif
echo inference finished

if ( -f "$BASE_PATH/baseline/seg_$SLURM_ARRAY_TASK_ID.h5" ) then
    echo Baseline already exists
else
    python3 sphere.py $TMPDIR $SLURM_ARRAY_TASK_ID
    cp $TMPDIR/seg_$SLURM_ARRAY_TASK_ID.h5 $BASE_PATH/baseline/
endif
echo baseline finished

rm -rf $TMPDIR
