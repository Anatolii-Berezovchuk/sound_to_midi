"""Первый эксперимент: не более 30 секунд аудио → MIDI и список нот."""

import argparse
import csv
import math
import os
from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Путь к аудиофайлу")
    parser.add_argument("--start", type=float, default=0, help="Начало отрывка в секундах (0)")
    parser.add_argument("--duration", type=float, default=25, help="Длина отрывка: от 1 до 30 секунд (25)")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "output")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Аудиофайл не найден: {args.input}")
    if not math.isfinite(args.start) or args.start < 0:
        parser.error("--start должен быть конечным числом не меньше 0")
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 30:
        parser.error("--duration должен быть от 1 до 30 секунд")

    name = f"{args.input.stem}_{args.start:g}s_{args.duration:g}s"
    clip_path = args.output_dir / f"{name}_source.wav"
    midi_path = args.output_dir / f"{name}.mid"
    notes_path = args.output_dir / f"{name}_notes.csv"
    for path in (clip_path, midi_path, notes_path):
        if path.exists():
            parser.error(f"Результат уже существует: {path}. Укажи другую --output-dir.")

    # Тяжёлые библиотеки загружаем после проверки аргументов.
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import librosa
    import pretty_midi
    import soundfile as sf
    from basic_pitch.constants import AUDIO_SAMPLE_RATE
    from basic_pitch.inference import predict

    started = time.perf_counter()
    print("Читаю выбранный отрывок...", flush=True)
    audio, sample_rate = librosa.load(
        str(args.input), sr=AUDIO_SAMPLE_RATE, mono=True,
        offset=args.start, duration=args.duration,
    )
    if audio.size == 0:
        raise ValueError("Отрывок пустой. Проверь время начала и длительность записи.")
    if not math.isfinite(float(abs(audio).max())):
        raise ValueError("В аудио обнаружены некорректные значения.")
    actual_duration = len(audio) / sample_rate
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sf.write(str(clip_path), audio, sample_rate, subtype="PCM_16")

    print(f"Распознаю {actual_duration:.2f} с аудио...", flush=True)
    _, midi, _ = predict(clip_path)
    # У фортепиано фиксированная высота нот: изменения высоты не экспортируем.
    for instrument in midi.instruments:
        instrument.program = 0
        instrument.pitch_bends.clear()
        instrument.notes = [note for note in instrument.notes if note.start < actual_duration]
        for note in instrument.notes:
            note.end = min(note.end, actual_duration)
    midi.write(str(midi_path))

    notes = sorted(
        (note for instrument in midi.instruments for note in instrument.notes),
        key=lambda note: (note.start, note.pitch),
    )
    with notes_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["start_seconds", "end_seconds", "duration_seconds", "midi_pitch", "note", "velocity"])
        for note in notes:
            writer.writerow([
                round(note.start, 4), round(note.end, 4), round(note.end - note.start, 4),
                note.pitch, pretty_midi.note_number_to_name(note.pitch), note.velocity,
            ])

    print(f"Готово: {len(notes)} нот, обработка {time.perf_counter() - started:.1f} с.")
    print(f"MIDI: {midi_path.resolve()}")
    print(f"Исходный отрывок: {clip_path.resolve()}")
    print(f"Таблица нот: {notes_path.resolve()}")
    if not notes:
        print("Модель не обнаружила нот. Попробуй другую запись.")
    return 0


if __name__ == "__main__":
    # Одинаковая кодировка для русского текста в терминале и при перенаправлении.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except (OSError, ValueError, ImportError, RuntimeError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)
