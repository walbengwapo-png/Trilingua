"""Small synthetic export check; no model installation or system configuration changes."""
import json
import subprocess
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent
FFMPEG = ROOT / "benchmark-tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"
FFPROBE = FFMPEG.with_name("ffprobe.exe")
DURATION = 15


def run(label, arguments):
    start = time.perf_counter()
    peak = 0
    lowest_available = psutil.virtual_memory().available
    log = ROOT / f"{label}.log"
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [str(FFMPEG), "-hide_banner", "-nostdin", "-y", *arguments],
            cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
        )
        watched = psutil.Process(process.pid)
        while process.poll() is None:
            try:
                peak = max(peak, watched.memory_info().rss)
                lowest_available = min(lowest_available, psutil.virtual_memory().available)
            except psutil.NoSuchProcess:
                break
            if time.perf_counter() - start > 90:
                process.kill()
                process.wait()
                raise TimeoutError(f"{label} exceeded 90 seconds")
            time.sleep(0.1)
    elapsed = time.perf_counter() - start
    return {
        "test": label, "exit_code": process.returncode,
        "wall_seconds": round(elapsed, 3),
        "source_duration_seconds": DURATION,
        "duration_divided_by_wall": round(DURATION / elapsed, 2),
        "ffmpeg_peak_working_set_MiB": round(peak / 1024**2, 1),
        "lowest_system_available_MiB": round(lowest_available / 1024**2, 1),
        "log": str(log),
    }


def main():
    (ROOT / "benchmark.ass").write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,1,2,80,80,280,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:07.50,Default,,0,0,0,,Captioned vertical export test\n"
        "Dialogue: 0,0:00:07.50,0:00:15.00,Default,,0,0,0,,Crop, scale, subtitles and audio\n",
        encoding="utf-8",
    )
    results = [run("prepare_source", [
        "-f", "lavfi", "-i", f"testsrc2=size=1920x1080:rate=30:duration={DURATION}",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={DURATION}",
        "-c:v", "libx264", "-threads", "4", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "benchmark_source.mp4",
    ])]
    assert results[0]["exit_code"] == 0, "Source creation failed; inspect prepare_source.log"
    for label, encoder in [
        ("x264_captioned", ["-c:v", "libx264", "-threads", "4", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]),
        ("qsv_captioned", ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "23"]),
    ]:
        result = run(label, [
            "-threads", "4", "-filter_threads", "2", "-i", "benchmark_source.mp4",
            "-vf", "crop=608:1080,scale=1080:1920,ass=benchmark.ass,format=nv12",
            *encoder, "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", f"{label}.mp4",
        ])
        if result["exit_code"] == 0:
            probe = subprocess.run([
                str(FFPROBE), "-v", "error", "-show_entries",
                "stream=codec_name,width,height,r_frame_rate:format=duration",
                "-of", "json", str(ROOT / f"{label}.mp4"),
            ], check=True, capture_output=True, text=True)
            result["probe"] = json.loads(probe.stdout)
            video = result["probe"]["streams"][0]
            assert (video["codec_name"], video["width"], video["height"]) == ("h264", 1080, 1920)
            assert abs(float(result["probe"]["format"]["duration"]) - DURATION) < 0.2
        results.append(result)
    report = {
        "scope": "15-second synthetic 1080p30 source; static crop to 1080x1920, ASS captions, AAC audio. Single run per encoder; existing background workload remains running. Not ASR, LLM, visual quality equivalence or full-app throughput.",
        "ffmpeg_version": subprocess.run([str(FFMPEG), "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0],
        "tests": results,
    }
    (ROOT / "benchmark-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if results[-1]["exit_code"] == 0:
        subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-ss", "2", "-i", str(ROOT / "qsv_captioned.mp4"), "-frames:v", "1", str(ROOT / "caption-check.png")], check=True)


if __name__ == "__main__":
    main()
