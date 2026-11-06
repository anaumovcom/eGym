"""Read local evidence, validate published assets, write a truthful v2 report. No network/DB."""

import json

from app.services.achievements.content import load_catalog, validate_catalog
from app.services.achievements.generation import BudgetLedger, durable_json
from app.services.achievements.media import AUDIO_ROOT, IMAGE_ROOT, checksum, load_manifest
from scripts.generate_achievement_media import current_audio, current_image


def audit() -> dict:
    ledger = BudgetLedger()
    catalog = load_catalog()
    assets = load_manifest().get('assets', {})
    tiers = [tier for line in catalog['lines'] for tier in line['tiers']]
    images, audio, missing_text, missing_images, missing_audio = [], [], [], [], []
    checksum_errors = []
    for tier in tiers:
        tier_id = tier['id']
        asset = assets.get(tier_id, {})
        if tier['contentOrigin'] != 'gpt-6.1-sol':
            missing_text.append(tier_id)
        (images if current_image(tier_id, asset) else missing_images).append(tier_id)
        name = asset.get('audio', {}).get('file', '')
        path = AUDIO_ROOT / name
        ready = current_audio(asset)
        if name and path.name == name and path.is_file() and asset.get('audioMetadata', {}).get('sha256'):
            if checksum(path) != asset['audioMetadata']['sha256']:
                checksum_errors.append(tier_id)
                ready = False
        (audio if ready else missing_audio).append(tier_id)
    validation_errors = validate_catalog(catalog, generated=True)
    report = {
        'version': 'v2', 'lines': len(catalog['lines']), 'tiers': len(tiers),
        'textReady': len(tiers) - len(missing_text), 'imagesReady': len(images), 'audioReady': len(audio),
        'missingText': missing_text, 'missingImages': missing_images, 'missingAudio': missing_audio,
        'checksumErrors': checksum_errors, 'validationErrors': validation_errors,
        'budget': ledger.summary(), 'exactProviderBilling': False,
        'budgetNote': 'Includes global historical holds and unresolved liabilities; not an invoice reconciliation.',
        'unresolved': [{'key': row['key'], 'status': row['status']} for row in ledger.attempts()
                       if row['status'] in {'sent', 'unsettled', 'reserved'}],
        'complete': not (missing_text or missing_images or missing_audio or checksum_errors or validation_errors),
        'imagesRoot': str(IMAGE_ROOT.relative_to(ledger.path.parents[1])),
    }
    durable_json(ledger.path.parent / 'v2' / 'generation-report.json', report)
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return report


if __name__ == '__main__':
    with BudgetLedger().job_lock():
        audit()