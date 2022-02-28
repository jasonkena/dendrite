#!/bin/tcsh
#SBATCH --job-name=generate-extracted # Job name
#SBATCH --array=0-49 # inclusive range
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task 20 # 1 cpu on single node
#SBATCH --mem=20gb # Job memory request
#SBATCH --time=120:00:00 # Time limit hrs:min:sec
#SBATCH --mail-type=BEGIN,END,FAIL. # Mail events (NONE, BEGIN, END, FAIL, ALL)
#SBATCH --mail-user=adhinart@bc.edu # Where to send mail
#SBATCH --partition=partial_nodes,full_nodes48,full_nodes64,gpuv100,gpua100,anzellos

module purge
module load anaconda
conda activate dendrite

cd /mmfs1/data/adhinart/dendrite

setenv TMPDIR /scratch/adhinart/dendrite/$SLURM_ARRAY_TASK_ID
rm -rf $TMPDIR
mkdir -p $TMPDIR
cp *.txt $TMPDIR
cp *.h5 $TMPDIR
cp *.npy $TMPDIR

python3 extract_seg.py $TMPDIR $SLURM_ARRAY_TASK_ID

rm -rf $TMPDIR