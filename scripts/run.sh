#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  تشغيل مشروع «استوديو بكسل»
#  الاستخدام:  bash scripts/run.sh [المنفذ]
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

PORT="${1:-8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

# إنشاء بيئة معزولة إن لم توجد
if [ ! -d ".venv" ]; then
  echo "→ إنشاء بيئة Python معزولة…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ تثبيت الاعتماديات…"
pip install --quiet --disable-pip-version-check -r requirements.txt

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  استوديو بكسل — المحرر يعمل الآن                          ║"
echo "╠══════════════════════════════════════════════════════════╣"
printf "║  الواجهة        : http://localhost:%s/\n" "$PORT"
printf "║  توثيق Swagger  : http://localhost:%s/api/docs\n" "$PORT"
printf "║  فحص الصحة      : http://localhost:%s/api/v1/health\n" "$PORT"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
