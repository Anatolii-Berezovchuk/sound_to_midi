"""Выравнивание ритма MIDI по сетке с вручную заданным темпом."""

import argparse
import copy
import math
from pathlib import Path
import sys

import pretty_midi


def snap_time(seconds: float, step: float) -> float:
    """Округлить время к ближайшему узлу, половину шага — вперёд."""
    return math.floor(seconds / step + 0.5) * step


def quantize(source: pretty_midi.PrettyMIDI, bpm: float, division: int,
             numerator: int, denominator: int) -> pretty_midi.PrettyMIDI:
    # division — число частей четверти: 4 соответствует шестнадцатым.
    step = 60 / bpm / division
    result = pretty_midi.PrettyMIDI(initial_tempo=bpm, resolution=960)
    result.time_signature_changes.append(
        pretty_midi.TimeSignature(numerator, denominator, 0)
    )
    result.key_signature_changes = copy.deepcopy(source.key_signature_changes)
    for original in source.instruments:
        instrument = copy.deepcopy(original)
        for note in instrument.notes:
            note.start = snap_time(note.start, step)
            note.end = max(note.start + step, snap_time(note.end, step))
        result.instruments.append(instrument)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Исходный MIDI")
    parser.add_argument("--bpm", type=float, required=True, help="Темп в четвертях в минуту")
    parser.add_argument("--division", type=int, choices=(2, 4, 8), default=4,
                        help="Частей четверти: 2 = восьмые, 4 = шестнадцатые, 8 = тридцать вторые")
    parser.add_argument("--meter", default="4/4", help="Размер, например 3/8 (по умолчанию 4/4)")
    parser.add_argument("--output", type=Path, help="Путь к новому MIDI")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Файл не найден: {args.input}")
    if not math.isfinite(args.bpm) or not 20 <= args.bpm <= 300:
        parser.error("--bpm должен быть конечным числом от 20 до 300")
    try:
        numerator, denominator = map(int, args.meter.split("/"))
    except ValueError:
        parser.error("Размер задаётся как 3/8 или 4/4")
    if not 1 <= numerator <= 255 or denominator not in (1, 2, 4, 8, 16, 32, 64):
        parser.error("Некорректный размер: числитель 1–255, знаменатель 1, 2, 4, 8, 16, 32 или 64")

    output = args.output or args.input.with_name(
        f"{args.input.stem}_quantized_{args.bpm:g}bpm_d{args.division}.mid"
    )
    if output.resolve() == args.input.resolve() or output.exists():
        parser.error(f"Файл уже существует или совпадает с исходником: {output}. Задай другой --output.")

    source = pretty_midi.PrettyMIDI(str(args.input))
    if not any(instrument.notes for instrument in source.instruments):
        parser.error("В исходном MIDI нет нот")
    if any(instrument.is_drum for instrument in source.instruments):
        parser.error("Этот эксперимент предназначен для MIDI без ударных")
    result = quantize(source, args.bpm, args.division, numerator, denominator)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.write(str(output))

    notes = [note for instrument in result.instruments for note in instrument.notes]
    shifts = [abs(new.start - old.start)
              for before, after in zip(source.instruments, result.instruments)
              for old, new in zip(before.notes, after.notes)]
    print(f"Готово: {len(notes)} нот, {args.bpm:g} BPM (четверть), размер {args.meter}.")
    print(f"Шаг сетки: {60 / args.bpm / args.division:.4f} с; минимальная длительность — один шаг.")
    print(f"Средний сдвиг начала ноты: {sum(shifts) / len(shifts):.4f} с.")
    print(f"Новый MIDI: {output.resolve()}")
    print("Темп задан вручную. Ошибки высоты нот, педаль и разделение рук не исправляются.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except (OSError, ValueError, EOFError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)
