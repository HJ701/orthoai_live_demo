#!/usr/bin/env bash
#SBATCH --job-name=exp1_7_orthopatientfusion
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --array=0-4
#SBATCH --output=slurm-%x-%A_%a.out
#SBATCH --error=slurm-%x-%A_%a.err

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/hamzah.al-omairi/Documents/orthoai}"
cd "${REPO_ROOT}"

CONDA_ENV_NAME="${CONDA_ENV_NAME:-ortho-deepspeedv}"
CONDA_SH=""
if [[ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]]; then
  CONDA_SH="${HOME}/miniconda3/etc/profile.d/conda.sh"
elif [[ -f "${HOME}/anaconda3/etc/profile.d/conda.sh" ]]; then
  CONDA_SH="${HOME}/anaconda3/etc/profile.d/conda.sh"
fi

if [[ -n "${CONDA_SH}" ]]; then
  # shellcheck source=/dev/null
  source "${CONDA_SH}"
  conda activate "${CONDA_ENV_NAME}"
  echo "[info] Activated conda env: ${CONDA_DEFAULT_ENV:-unknown}"
else
  echo "[warn] conda.sh not found; running without conda activation."
fi

RGB_CSV="${RGB_CSV:-data/Orthoai-cleaned-dataset-dr-Mohammed/rgb_intraoral_labels_matched_from_rgb_intraoral_cleaned.csv}"
OPG_CSV="${OPG_CSV:-data/Orthoai-cleaned-dataset-dr-Mohammed/opg_cleaned.csv}"
STRICT_CLEANED_CSV="${STRICT_CLEANED_CSV:-0}"
REQUIRED_MODALITIES="${REQUIRED_MODALITIES:-rgb,xray}"
MIN_IMAGES_PER_PATIENT="${MIN_IMAGES_PER_PATIENT:-2}"
MAX_IMAGES_PER_PATIENT="${MAX_IMAGES_PER_PATIENT:-8}"
MAX_IMAGES_PER_VIEW="${MAX_IMAGES_PER_VIEW:-2}"
SPLIT_RATIOS="${SPLIT_RATIOS:-0.70,0.15,0.15}"

OPG_ENCODER_NAME="${OPG_ENCODER_NAME:-convnext_tiny}"
RGB_ENCODER_NAME="${RGB_ENCODER_NAME:-convnext_tiny}"
ENCODER_INIT_SOURCE="${ENCODER_INIT_SOURCE:-imagenet}"
SHARED_ENCODER="${SHARED_ENCODER:-0}"
FREEZE_ENCODERS="${FREEZE_ENCODERS:-0}"
TOKEN_DIM="${TOKEN_DIM:-512}"
FUSION_LAYERS="${FUSION_LAYERS:-2}"
FUSION_HEADS="${FUSION_HEADS:-8}"
DIAGNOSIS_QUERIES="${DIAGNOSIS_QUERIES:-1}"
DROPOUT="${DROPOUT:-0.25}"

IMAGE_SIZE="${IMAGE_SIZE:-224}"
EPOCHS="${EPOCHS:-60}"
MIN_EPOCHS="${MIN_EPOCHS:-15}"
EARLY_STOPPING_PATIENCE="${EARLY_STOPPING_PATIENCE:-10}"
BATCH_SIZE="${BATCH_SIZE:-4}"
ACCUM_STEPS="${ACCUM_STEPS:-1}"
NUM_WORKERS="${NUM_WORKERS:-8}"
ENCODER_LR="${ENCODER_LR:-1e-5}"
FUSION_LR="${FUSION_LR:-5e-4}"
MIN_LR_SCALE="${MIN_LR_SCALE:-0.10}"
WARMUP_EPOCHS="${WARMUP_EPOCHS:-5}"
WEIGHT_DECAY="${WEIGHT_DECAY:-0.05}"
CRITERION="${CRITERION:-focal}"
FOCAL_GAMMA="${FOCAL_GAMMA:-2.0}"
CLASS_WEIGHT_MODE="${CLASS_WEIGHT_MODE:-sqrt_balanced}"
AUX_LOSS_WEIGHT="${AUX_LOSS_WEIGHT:-0.25}"
SAVE_EVERY="${SAVE_EVERY:-5}"
SEED="${SEED:-42}"
DEVICE="${DEVICE:-cuda}"
USE_AMP="${USE_AMP:-1}"

AUTO_RESUME="${AUTO_RESUME:-1}"
SKIP_COMPLETED="${SKIP_COMPLETED:-1}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

EXPERIMENT_LIST="${EXPERIMENT_LIST:-late_fusion,attention_mil,set_transformer,cross_attention,auxiliary_heads}"
IFS=',' read -r -a EXPERIMENTS <<< "${EXPERIMENT_LIST}"
TASK_ID="${SLURM_ARRAY_TASK_ID:-0}"

if (( TASK_ID < 0 || TASK_ID >= ${#EXPERIMENTS[@]} )); then
  echo "[error] SLURM_ARRAY_TASK_ID=${TASK_ID} outside experiment list size ${#EXPERIMENTS[@]}"
  exit 2
fi

EXP_NAME="$(echo "${EXPERIMENTS[$TASK_ID]}" | xargs)"
case "${EXP_NAME}" in
  late_fusion) PY_SCRIPT="OrthoPatientFusion/experiment_01_late_fusion.py" ;;
  attention_mil) PY_SCRIPT="OrthoPatientFusion/experiment_02_attention_mil.py" ;;
  set_transformer) PY_SCRIPT="OrthoPatientFusion/experiment_03_set_transformer.py" ;;
  cross_attention) PY_SCRIPT="OrthoPatientFusion/experiment_04_cross_attention.py" ;;
  auxiliary_heads) PY_SCRIPT="OrthoPatientFusion/experiment_05_auxiliary_heads.py" ;;
  *)
    echo "[error] Unsupported Exp 1.7 experiment: ${EXP_NAME}"
    exit 2
    ;;
esac

RUN_ID="${SLURM_ARRAY_JOB_ID:-${SLURM_JOB_ID:-local}}"
RUN_TAG="${RUN_TAG:-exp1_7_orthopatientfusion_$(date +%Y%m%d_%H%M%S)_job${RUN_ID}}"
OUT_BASE_DIR="${OUT_BASE_DIR:-models/exp1_7_orthopatientfusion_runs}"
RUN_ROOT="${OUT_BASE_DIR}/${RUN_TAG}"
OUT_DIR="${RUN_ROOT}/${EXP_NAME}"
RUN_PROGRESS="${OUT_DIR}/progress.log"
METRICS_FILE="${OUT_DIR}/train_log.jsonl"
FINAL_RESULTS_FILE="${OUT_DIR}/final_results.json"

mkdir -p "${OUT_DIR}"
export PYTHONUNBUFFERED=1

{
  echo "[info] Start time: $(date -Iseconds)"
  echo "[info] Slurm job id: ${SLURM_JOB_ID:-N/A}"
  echo "[info] Slurm array job id: ${SLURM_ARRAY_JOB_ID:-N/A}"
  echo "[info] Slurm array task id: ${SLURM_ARRAY_TASK_ID:-N/A}"
  echo "[info] Experiment: ${EXP_NAME}"
  echo "[info] Python script: ${PY_SCRIPT}"
  echo "[info] Output dir: ${OUT_DIR}"
  echo "[info] Required modalities: ${REQUIRED_MODALITIES:-<none>}"
  echo "[info] GPU request: ${CUDA_VISIBLE_DEVICES:-slurm-managed}"
  echo "[info] Conda env: ${CONDA_DEFAULT_ENV:-not-active}"
} | tee -a "${RUN_PROGRESS}"

if [[ "${SKIP_COMPLETED}" == "1" && -f "${FINAL_RESULTS_FILE}" ]]; then
  echo "[info] final_results.json already exists, skipping ${EXP_NAME}." | tee -a "${RUN_PROGRESS}"
  exit 0
fi

cmd=(
  python3 -u "${PY_SCRIPT}"
  --experiment "${EXP_NAME}"
  --rgb-csv "${RGB_CSV}"
  --opg-csv "${OPG_CSV}"
  --required-modalities "${REQUIRED_MODALITIES}"
  --min-images-per-patient "${MIN_IMAGES_PER_PATIENT}"
  --max-images-per-patient "${MAX_IMAGES_PER_PATIENT}"
  --max-images-per-view "${MAX_IMAGES_PER_VIEW}"
  --split-ratios "${SPLIT_RATIOS}"
  --opg-encoder-name "${OPG_ENCODER_NAME}"
  --rgb-encoder-name "${RGB_ENCODER_NAME}"
  --encoder-init-source "${ENCODER_INIT_SOURCE}"
  --token-dim "${TOKEN_DIM}"
  --fusion-layers "${FUSION_LAYERS}"
  --fusion-heads "${FUSION_HEADS}"
  --diagnosis-queries "${DIAGNOSIS_QUERIES}"
  --dropout "${DROPOUT}"
  --image-size "${IMAGE_SIZE}"
  --epochs "${EPOCHS}"
  --min-epochs "${MIN_EPOCHS}"
  --early-stopping-patience "${EARLY_STOPPING_PATIENCE}"
  --batch-size "${BATCH_SIZE}"
  --accum-steps "${ACCUM_STEPS}"
  --num-workers "${NUM_WORKERS}"
  --encoder-lr "${ENCODER_LR}"
  --fusion-lr "${FUSION_LR}"
  --min-lr-scale "${MIN_LR_SCALE}"
  --warmup-epochs "${WARMUP_EPOCHS}"
  --weight-decay "${WEIGHT_DECAY}"
  --criterion "${CRITERION}"
  --focal-gamma "${FOCAL_GAMMA}"
  --class-weight-mode "${CLASS_WEIGHT_MODE}"
  --aux-loss-weight "${AUX_LOSS_WEIGHT}"
  --save-every "${SAVE_EVERY}"
  --seed "${SEED}"
  --device "${DEVICE}"
  --out-dir "${OUT_DIR}"
  --checkpoint-name "exp1_7_${EXP_NAME}.ckpt"
)

if [[ "${STRICT_CLEANED_CSV}" == "1" ]]; then
  cmd+=(--strict-cleaned-csv)
fi
if [[ "${SHARED_ENCODER}" == "1" ]]; then
  cmd+=(--shared-encoder)
fi
if [[ "${FREEZE_ENCODERS}" == "1" ]]; then
  cmd+=(--freeze-encoders)
fi
if [[ "${USE_AMP}" == "1" ]]; then
  cmd+=(--amp)
fi
if [[ "${AUTO_RESUME}" == "1" && -f "${OUT_DIR}/last.ckpt" ]]; then
  cmd+=(--resume "${OUT_DIR}/last.ckpt")
fi
if [[ -n "${EXTRA_ARGS}" ]]; then
  # shellcheck disable=SC2206
  extra_array=(${EXTRA_ARGS})
  cmd+=("${extra_array[@]}")
fi

{
  printf "[info] Command:"
  printf " %q" "${cmd[@]}"
  printf "\n"
} | tee -a "${RUN_PROGRESS}"

("${cmd[@]}") 2>&1 | tee -a "${RUN_PROGRESS}" &
TRAIN_PID=$!

(
  while kill -0 "${TRAIN_PID}" 2>/dev/null; do
    [[ -f "${METRICS_FILE}" ]] && break
    sleep 5
  done
  if [[ -f "${METRICS_FILE}" ]]; then
    echo "[info] Streaming per-epoch metrics from ${METRICS_FILE}" | tee -a "${RUN_PROGRESS}"
    tail --pid="${TRAIN_PID}" -n +1 -F "${METRICS_FILE}" \
      | sed -u "s/^/[epoch-metrics ${EXP_NAME}] /" \
      | tee -a "${RUN_PROGRESS}"
  fi
) &
MONITOR_PID=$!

wait "${TRAIN_PID}" || TRAIN_STATUS=$?
TRAIN_STATUS="${TRAIN_STATUS:-0}"
wait "${MONITOR_PID}" || true

if [[ "${TRAIN_STATUS}" != "0" ]]; then
  echo "[error] ${EXP_NAME} failed with exit code ${TRAIN_STATUS}" | tee -a "${RUN_PROGRESS}"
  exit "${TRAIN_STATUS}"
fi

echo "[done] ${EXP_NAME} completed at $(date -Iseconds)" | tee -a "${RUN_PROGRESS}"
