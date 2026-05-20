# OrthoPatientFusion - Exp 1.7

Patient-level multimodal malocclusion classification.

The Exp 1.7 data contract is:

```text
patient_id -> {OPG X-ray, intraoral frontal, buccal, occlusal, ...} -> one diagnosis
```

This differs from Exp 1.6, which is multi-encoder image-level fusion. Exp 1.7 groups cleaned CSV rows by `Patient_ID`, infers view labels from filenames, and trains on patient bags.

## Experiments

- `experiment_01_late_fusion.py`: image logits averaged to patient logits.
- `experiment_02_attention_mil.py`: attention multiple-instance learning over patient images.
- `experiment_03_set_transformer.py`: Set Transformer-style patient bag fusion.
- `experiment_04_cross_attention.py`: learned diagnosis query attends to patient image tokens.
- `experiment_05_auxiliary_heads.py`: cross-attention plus image/modality auxiliary supervision.

Shared implementation lives in:

```text
OrthoPatientFusion/ortho_patient_fusion_core.py
```

## SLURM

Submit all five experiments as a GPU array job:

```bash
sbatch OrthoPatientFusion/submit_exp1_7_orthopatientfusion.slurm.sh
```

Default outputs:

```text
models/exp1_7_orthopatientfusion_runs/<run_tag>/<experiment>/
```

Each experiment writes:

```text
metadata.json
train_patients.jsonl
val_patients.jsonl
test_patients.jsonl
train_log.jsonl
best.ckpt
last.ckpt
exp1_7_<experiment>.ckpt
final_results.json
graphs/
```

Aggregate completed runs:

```bash
python3 OrthoPatientFusion/aggregate_exp1_7_results.py models/exp1_7_orthopatientfusion_runs/<run_tag>
```

## Useful Overrides

```bash
EPOCHS=80 BATCH_SIZE=4 MAX_IMAGES_PER_PATIENT=8 \
sbatch OrthoPatientFusion/submit_exp1_7_orthopatientfusion.slurm.sh
```

By default the patient bags require both RGB intraoral and X-ray samples:

```bash
REQUIRED_MODALITIES=rgb,xray
```

To include incomplete patient bags:

```bash
REQUIRED_MODALITIES= sbatch OrthoPatientFusion/submit_exp1_7_orthopatientfusion.slurm.sh
```
