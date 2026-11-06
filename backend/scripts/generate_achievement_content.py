"""Generate variable-tier editorial achievement texts in resumable two-line batches.

Dry-run writes the deterministic skeleton and implementation documents but performs no network calls.
Paid use: python scripts/generate_achievement_content.py --confirm-paid [--limit-lines 5]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from app.services.achievements.content import (
    CATALOG_PATH,
    empty_catalog,
    load_catalog,
    reconcile_catalog,
    save_catalog,
    validate_catalog,
    write_markdown,
)
from app.services.achievements.generation import BudgetLedger, durable_bytes, read_credential, token_cost
from app.services.achievements.rules import CONTENT_VERSION, RULES

MODEL = "gpt-6.1-sol"
URL = "https://api.openai.com/v1/responses"
ROOT = Path(__file__).resolve().parents[2]
MD_PATH = ROOT / "plan" / "v2" / "19-achievements-content.md"
EDITORIAL_STYLE = "v2"

INSTRUCTIONS = """Ты — главный редактор коллекции достижений фитнес-приложения Forma.
Создай яркий русский editorial-контент строго по переданным deterministic rules. Не меняй ID, условия, пороги, единицы,
applicability или редкость. В линии от 3 до 6 ступеней: верни ровно фактически переданный список tiers,
без добавления, пропуска и перестановки ID. tierCount — число ступеней линии, isFinal отмечает её настоящий финал.
Сохрани исходный смысл каждой линии и конкретного порога; не подменяй его общей похвалой.

Для каждой ступени верни:
- title: 2–6 слов, короткое запоминающееся название награды, не копия названий соседних ступеней;
- phrase: 1–2 предложения, 20–240 символов, обращение на «ты», конкретно об условии и пороге;
- imagePrompt: ТОЛЬКО уникальный английский концепт сцены, примерно 150–300 символов, без общего art-direction;
- fishMarkup: русская фраза дословно, с эмоциональной разметкой Fish Drama 3;
- audioText: та же фраза без разметки.

Тон: дерзко, смешно и поддерживающе, без мата. Можно иронию, спортивные метафоры, неожиданные предметы,
мини-сцены и добрые подколы над железом/ленью/абсурдом ситуации, но не над человеком. Не повторяй шаблон
«Ты молодец», не начинай все фразы одинаково, не используй канцелярит. Редкость влияет на размах, не на ценность человека.

Жёсткие запреты: никакой оценки внешности/веса тела, медицинских обещаний, идеальной техники, ежедневного принуждения,
штрафов за отдых, призывов повышать вес вне плана, сокращать отдых, терпеть боль или избегать СТОП.
Накопительные награды описывай как историю, не как задачу сделать всё сегодня. Частичная тренировка — уважительно.
Для insufficient-data веток не обещай измерений, которых нет.

Внутри линии придумай одно узнаваемое семейство визуальных субъектов: тот же герой/предмет развивается
от ступени к ступени через действие, масштаб и сцену. Не заменяй его несвязанными метафорами.
Финал определяется isFinal и tier/tierCount, а НЕ номером 3 и НЕ редкостью. Настоящая финальная ступень —
самая смешная, изобретательная и запоминающаяся кульминация линии; предыдущие ступени готовят её.
Визуальный контекст v2: сохранить point-up rounded hexagonal badge, узкий насыщенный bevel,
тёмную inset-панель и читаемый объёмный stylized 2.5D центральный сюжет, единые свет и силуэт.
Никаких нижних ромбов, корон, драгоценных камней, кристаллов, подвесок или декоративных украшений
ни при какой редкости. Нижняя грань чистая. Без текста, цифр, логотипов, круглых медалей и заклёпок.
В imagePrompt описывай только субъект, действие, композицию сцены и отличительные детали данной ступени:
не копируй эти правила стиля, рамку, фон, палитру редкости, технические параметры или negative prompt.
Общий art-direction добавляет отдельный visual pipeline; здесь нужен только уникальный концепт.

Fish Drama 3: добавь 1–3 квадратные ремарки эмоций/подачи и при необходимости paired <emphasis>…</emphasis>,
<soft>…</soft>, <slow>…</slow>. Не используй speaker/phoneme tags. Не перегружай короткую фразу.
Эмоции зависят прежде всего от относительной ступени tier/tierCount, не только от редкости:
warm → playful → confident → excited → triumphant (для 3–8 ступеней адаптируй плавную прогрессию).
В начале тепло и лёгкая улыбка, дальше больше уверенности и азарта; на isFinal — триумфальная подача
с короткой комедийной паузой перед смешной развязкой, например через <slow>, не меняя произносимые слова.
Без разметки markup должен дословно совпадать с audioText и phrase. Учитывай, что разметка тарифицируется по UTF-8 bytes.

Верни только JSON по schema. Каждая фраза и каждый визуальный концепт должны отличаться от остальных в этом ответе.
"""


def schema() -> dict[str, Any]:
    tier = {"type": "object", "additionalProperties": False,
            "properties": {key: {"type": "string"} for key in ("id", "title", "phrase", "imagePrompt", "fishMarkup", "audioText")},
            "required": ["id", "title", "phrase", "imagePrompt", "fishMarkup", "audioText"]}
    line = {"type": "object", "additionalProperties": False,
            "properties": {"id": {"type": "string"}, "tiers": {"type": "array", "minItems": 3, "maxItems": 8, "items": tier}},
            "required": ["id", "tiers"]}
    return {"type": "object", "additionalProperties": False,
            "properties": {"lines": {"type": "array", "minItems": 1, "maxItems": 5, "items": line}}, "required": ["lines"]}


def batch_payload(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for line in lines:
        result.append({key: line[key] for key in (
            "id", "group", "groupName", "metric", "description", "unit", "applicability", "thresholds"
        )} | {"tierCount": len(line["tiers"]),
            "tiers": [{"id": tier["id"], "tier": tier["tier"], "tierName": tier["tierName"],
                       "tierCount": tier["tierCount"], "isFinal": tier["isFinal"],
                       "threshold": tier["threshold"], "rarity": tier["rarity"]} for tier in line["tiers"]]})
    return result


def output_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    return str(part["text"])
    raise RuntimeError("provider_incomplete")


def request_batch(client: httpx.Client, body: dict[str, Any], key: str) -> httpx.Response:
    """Network only: the coordinator owns all persistence and budget accounting."""
    return client.post(URL, json=body, headers={"Authorization": f"Bearer {key}"})


def merge_batch(catalog: dict[str, Any], original: list[dict[str, Any]], answer: dict[str, Any]) -> None:
    expected = {line["id"]: line for line in original}
    rows = answer.get("lines", [])
    returned = {line.get("id"): line for line in rows}
    if len(rows) != len(expected) or set(returned) != set(expected):
        raise RuntimeError("provider_line_ids_mismatch")
    candidate = deepcopy(catalog)
    for line_id, source in expected.items():
        tiers = returned[line_id].get("tiers", [])
        by_id = {tier.get("id"): tier for tier in tiers}
        if len(tiers) != len(source["tiers"]) or set(by_id) != {tier["id"] for tier in source["tiers"]}:
            raise RuntimeError(f"provider_tier_ids_mismatch:{line_id}")
        for target in candidate["lines"][next(i for i, row in enumerate(candidate["lines"]) if row["id"] == line_id)]["tiers"]:
            generated = by_id[target["id"]]
            for key in ("title", "phrase", "imagePrompt", "fishMarkup", "audioText"):
                value = generated.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise RuntimeError(f"provider_empty_field:{target['id']}:{key}")
                target[key] = value.strip()
            target["contentOrigin"] = MODEL
            target["editorialStyle"] = EDITORIAL_STYLE
    # Batch-specific semantic checks; full catalog is checked after all batches.
    subset = {"lines": [line for line in candidate["lines"] if line["id"] in expected]}
    total = sum(len(rule["thresholds"]) for rule in RULES)
    errors = [error for error in validate_catalog(subset, generated=True)
              if not error.startswith((f"expected {len(RULES)} lines, got ", "line IDs differ from deterministic rules",
                                       f"expected {total} tiers, got ",
                                       "unexpected rarity distribution"))]
    if errors:
        raise RuntimeError("content_validation:" + ";".join(errors[:4]))
    generated_phrases = [tier["phrase"].casefold() for line in candidate["lines"] for tier in line["tiers"]
                         if tier["contentOrigin"] == MODEL]
    if len(generated_phrases) != len(set(generated_phrases)):
        raise RuntimeError("duplicate_generated_phrase")
    catalog["lines"] = candidate["lines"]


def _restore_settled_legacy_responses(catalog: dict[str, Any], ledger: BudgetLedger,
                                      blocked: set[str]) -> set[str]:
    """Recover missing lines only from responses linked to settled request IDs."""
    if not blocked:
        return blocked
    by_id = {line["id"]: line for line in catalog["lines"]}
    settled_ids = {row.get("requestId") for row in ledger.attempts("openai")
                   if row["kind"] == "text" and row["status"] == "settled" and row.get("requestId")}
    restored: set[str] = set()
    for responses_root in (ledger.path.parent / "responses", ledger.path.parent / "v2" / "responses"):
        if not responses_root.is_dir():
            continue
        for path in sorted(responses_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("id") not in settled_ids or payload.get("model") != MODEL:
                    continue
                answer = json.loads(output_text(payload))
            except (OSError, ValueError, RuntimeError):
                continue
            answer_by_id = {line.get("id"): line for line in answer.get("lines", [])}
            for line_id in sorted(blocked - restored):
                generated = answer_by_id.get(line_id)
                if generated is None or all(tier["contentOrigin"] == MODEL for tier in by_id[line_id]["tiers"]):
                    continue
                try:
                    merge_batch(catalog, [by_id[line_id]], {"lines": [generated]})
                except RuntimeError as exc:
                    raise RuntimeError(f"saved_response_invalid:{line_id}:{payload['id']}") from exc
                restored.add(line_id)
    if restored:
        catalog["textModel"] = MODEL
    return blocked - restored


def restore_batches(catalog: dict[str, Any], ledger: BudgetLedger) -> set[str]:
    """Replay paid responses before batching, even if the operator changes batch size.

    Unknown outcomes (or settled calls whose response was lost) block their original
    lines, not merely the old batch key: regrouping must never buy them a second time.
    """
    prefix = f"text:{CONTENT_VERSION}:{EDITORIAL_STYLE}:"
    by_id = {line["id"]: line for line in catalog["lines"]}
    blocked: set[str] = set()
    for attempt in ledger.attempts("openai"):
        key = attempt["key"]
        if not key.startswith(prefix):
            # A content-version bump is not permission to repay an older unknown
            # v2 dispatch. IDs, not regrouped batch/version keys, own liabilities.
            parts = key.split(':')
            if (len(parts) > 3 and parts[0] == 'text' and parts[2] == EDITORIAL_STYLE
                    and attempt['status'] in {'sent', 'unsettled', 'settled'}):
                blocked.update(line_id for line_id in parts[3:] if line_id in by_id
                               and any(tier['contentOrigin'] != MODEL for tier in by_id[line_id]['tiers']))
            continue
        lines = [by_id[line_id] for line_id in key[len(prefix):].split(":") if line_id in by_id]
        response_path = ledger.path.parent / "v2" / "responses" / f"{key.replace(':', '-')}.json"
        if response_path.is_file():
            try:
                payload = json.loads(response_path.read_text(encoding="utf-8"))
                answer = json.loads(output_text(payload))
                if attempt["status"] != "settled":
                    ledger.settle(key, token_cost(MODEL, payload.get("usage") or {}),
                                  request_id=str(payload.get("id", "")), usage=payload.get("usage") or {})
                # Never replay old editorial over already accepted/reviewed content.
                if any(t['contentOrigin'] != MODEL for line in lines for t in line['tiers']):
                    merge_batch(catalog, lines, answer)
            except Exception as exc:
                # Saved bytes are evidence of a paid outcome, never permission to retry.
                raise RuntimeError(f"saved_response_invalid:{key}") from exc
            catalog["textModel"] = MODEL
        elif attempt["status"] in {"sent", "unsettled", "settled"}:
            ids = [line["id"] for line in lines]
            blocked.update(ids)
            print(json.dumps({"skippedUnresolvedBatch": ids}, ensure_ascii=False), flush=True)
    return _restore_settled_legacy_responses(catalog, ledger, blocked)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--recover-only", action="store_true", help="Restore settled local responses; never dispatch")
    parser.add_argument("--cap-openai", type=float, default=36.0)
    parser.add_argument("--limit-lines", type=int, default=len(RULES))
    parser.add_argument("--batch-size", type=int, default=2, choices=range(1, 6))
    parser.add_argument("--concurrency", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--retry-line", action="append", default=[],
                        help="Explicitly repay one unresolved line; original liabilities remain recorded")
    args = parser.parse_args()
    if args.retry_line and not args.confirm_paid:
        parser.error("--retry-line requires --confirm-paid")

    path = CATALOG_PATH
    catalog = load_catalog(path) if path.is_file() else empty_catalog()
    reconciled = reconcile_catalog(catalog)
    if reconciled != catalog and path.is_file():
        import hashlib
        original = path.read_bytes()
        archive = path.with_name(f"catalog-before-{hashlib.sha256(original).hexdigest()[:16]}.json")
        if not archive.exists():
            durable_bytes(archive, original)
    catalog = reconciled
    save_catalog(catalog, path)
    write_markdown(catalog, MD_PATH)
    pending = [line for line in catalog["lines"] if any(t["contentOrigin"] != MODEL for t in line["tiers"])]
    pending = pending[:max(0, args.limit_lines)]
    estimate = {"pendingLines": len(pending), "pendingTiers": sum(len(line["tiers"]) for line in pending),
                "model": MODEL, "paid": bool(args.confirm_paid)}
    print(json.dumps(estimate, ensure_ascii=False), flush=True)
    if not args.confirm_paid and not args.recover_only:
        return 0
    if not pending:
        errors = validate_catalog(catalog, generated=True)
        if errors:
            raise RuntimeError(";".join(errors[:20]))
        write_markdown(catalog, MD_PATH)
        return 0

    ledger = BudgetLedger(openai_cap_usd=args.cap_openai)
    blocked = restore_batches(catalog, ledger)
    known_ids = {line["id"] for line in catalog["lines"]}
    if unknown := set(args.retry_line) - known_ids:
        raise RuntimeError(f"unknown_retry_lines:{sorted(unknown)}")
    blocked.difference_update(args.retry_line)
    save_catalog(catalog, path)
    write_markdown(catalog, MD_PATH)
    if args.recover_only:
        remaining = sum(any(tier["contentOrigin"] != MODEL for tier in line["tiers"]) for line in catalog["lines"])
        print(json.dumps({"complete": remaining == 0, "remainingLines": remaining,
                          "recoveredOnly": True, "budget": ledger.summary()}, ensure_ascii=False), flush=True)
        return 0
    pending = [line for line in catalog["lines"] if line["id"] not in blocked
               and any(tier["contentOrigin"] != MODEL for tier in line["tiers"])
               and (not args.retry_line or line["id"] in args.retry_line)]
    pending = pending[:max(0, args.limit_lines)]
    key = read_credential("openai") if pending else ""
    max_output = 16_000
    in_flight: dict[Future[httpx.Response], tuple[list[dict[str, Any]], str, Path]] = {}
    offset = processed = 0
    failure: BaseException | None = None

    def record_failure(exc: BaseException, attempt_key: str) -> None:
        nonlocal failure
        if failure is None:
            failure = exc
        if attempt_key:
            try:
                ledger.unsettled(attempt_key)
            except BaseException:
                # Even a broken ledger must not discard other paid responses.
                # The durable sent marker already prevents an automatic retry.
                pass

    with httpx.Client(timeout=180, follow_redirects=False, trust_env=False) as client, \
            ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        while in_flight or (failure is None and offset < len(pending)):
            while failure is None and offset < len(pending) and len(in_flight) < args.concurrency:
                # Observe finished failures before buying another batch.
                if any(future.done() for future in in_flight):
                    break
                attempt_key = ""
                try:
                    lines = pending[offset:offset + args.batch_size]
                    ids = [line["id"] for line in lines]
                    body = {"model": MODEL, "store": False, "instructions": INSTRUCTIONS,
                            "input": [{"role": "user", "content": json.dumps(batch_payload(lines), ensure_ascii=False)}],
                            "text": {"format": {"type": "json_schema", "name": "achievement_editorial_batch",
                                                "schema": schema(), "strict": True}},
                            "reasoning": {"effort": "high"}, "max_output_tokens": max_output}
                    input_bound = min(1_000_000, len(json.dumps(body, ensure_ascii=False).encode()) * 2 + 1024)
                    reserve = token_cost(MODEL, {"input_tokens": input_bound, "output_tokens": max_output})
                    attempt_key = f"text:{CONTENT_VERSION}:{EDITORIAL_STYLE}:" + ":".join(ids)
                    if args.retry_line:
                        attempt_key += ":retry1"
                    response_path = ledger.path.parent / "v2" / "responses" / f"{attempt_key.replace(':', '-')}.json"
                    if response_path.is_file():
                        merge_batch(catalog, lines, json.loads(output_text(json.loads(response_path.read_text(encoding="utf-8")))))
                        save_catalog(catalog, path)
                        write_markdown(catalog, MD_PATH)
                        offset += len(lines)
                        continue
                    previous = ledger.find(attempt_key)
                    if previous and previous["status"] in {"sent", "unsettled", "settled"}:
                        print(json.dumps({"skippedUnresolvedBatch": ids}, ensure_ascii=False), flush=True)
                        offset += len(lines)
                        continue
                    if ledger.reserve(attempt_key, "openai", "text", MODEL, reserve) is None:
                        print(json.dumps({"cachedTextBatch": ids}, ensure_ascii=False), flush=True)
                        offset += len(lines)
                        continue
                    print(json.dumps({"stage": "text", "startingBatch": ids,
                                      "processedLines": processed, "queuedLines": len(pending)}, ensure_ascii=False), flush=True)
                    ledger.sent(attempt_key)
                    future = executor.submit(request_batch, client, body, key)
                    in_flight[future] = (lines, attempt_key, response_path)
                    offset += len(lines)
                except BaseException as exc:
                    record_failure(exc, attempt_key)
            if not in_flight:
                break
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                lines, attempt_key, response_path = in_flight.pop(future)
                ids = [line["id"] for line in lines]
                try:
                    response = future.result()
                    # Preserve even malformed/non-200 bodies before parsing or settlement.
                    response_path.parent.mkdir(parents=True, exist_ok=True)
                    durable_bytes(response_path, response.content)
                    if response.status_code != 200:
                        raise RuntimeError(f"provider_http_{response.status_code}")
                    payload = response.json()
                    usage = payload.get("usage") or {}
                    ledger.settle(attempt_key, token_cost(MODEL, usage), request_id=str(payload.get("id", "")), usage=usage)
                    merge_batch(catalog, lines, json.loads(output_text(payload)))
                    catalog["textModel"] = MODEL
                    save_catalog(catalog, path)
                    write_markdown(catalog, MD_PATH)
                    processed += len(lines)
                    print(json.dumps({"completedTextBatch": ids, "processedLines": processed,
                                      "queuedLines": len(pending), "budget": ledger.summary()}, ensure_ascii=False), flush=True)
                except BaseException as exc:
                    record_failure(exc, attempt_key)
                    print(json.dumps({"failedTextBatch": ids, "error": type(exc).__name__}, ensure_ascii=False), flush=True)
        if failure is not None:
            raise failure
    remaining = sum(any(tier["contentOrigin"] != MODEL for tier in line["tiers"]) for line in catalog["lines"])
    if remaining:
        print(json.dumps({"complete": False, "remainingLines": remaining, "budget": ledger.summary()}, ensure_ascii=False), flush=True)
        return 0
    errors = validate_catalog(catalog, generated=True)
    if errors:
        raise RuntimeError(";".join(errors[:20]))
    print(json.dumps({"complete": True, "lines": len(catalog["lines"]),
                      "tiers": sum(len(line["tiers"]) for line in catalog["lines"]),
                      "budget": ledger.summary()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with BudgetLedger().job_lock():
        raise SystemExit(main())
