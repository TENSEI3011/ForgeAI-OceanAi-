# Reproduce the committed demo runs (Windows PowerShell). Each build takes ~1-1.5 h on a 4 GB laptop GPU.
$env:PYTHONIOENCODING = "utf-8"
python -m forgeai build --brief-file demos/ship_spares/brief.txt --docs demos/ship_spares/docs --out runs/ship_spares `
    --answers demos/ship_spares/answers.json --non-interactive *> runs/ship_spares.log
python -m forgeai build --brief-file demos/hr_policy/brief.txt --docs demos/hr_policy/docs --out runs/hr_policy `
    --answers demos/hr_policy/answers.json --non-interactive --tournament *> runs/hr_policy.log
python scripts/run_stretch.py runs/hr_policy *> runs/hr_policy_stretch.log
python -m forgeai build --brief-file demos/brief_unseen_example/brief.txt --docs demos/brief_unseen_example/docs `
    --out runs/sms_unseen_example --non-interactive *> runs/sms_unseen_example.log
