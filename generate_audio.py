#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在本机合成本问卷要用的全部 40 个假词。

为什么有这个脚本
    这 40 个词来自 ../词对抽样/drawn_20_pairs.csv —— Study 3b 四十个字母对里
    走随机支的那 20 个，每个对比一组载体词，主种子 20260824。
    管线参数与 generate_audio_2b_mac.py 逐字相同。

管线（与 generate_audio_two_sets_mac.py / generate_audio_pilot2_mac.py 逐字相同）
    edge-tts 合成 → ffmpeg loudnorm 两遍归一化
    VOICE = en-US-AriaNeural   RATE = -10%
    I = -16 LUFS   TP = -1.5   LRA = 11

依赖   pip install edge-tts     brew install ffmpeg
用法   cd github_random_branch && python3 generate_audio.py
       跑完直接打开 items_random_branch.csv

只写本目录的 mp3，不动 ../音频/、../2b词试听/、../study2词试听/ 下的任何东西。
"""
import asyncio, os, re, json, subprocess, sys

try:
    import edge_tts
except ImportError:
    sys.exit('缺 edge-tts：pip install edge-tts')

VOICE       = "en-US-AriaNeural"
RATE        = "-10%"
TARGET_LUFS = "-16"
TRUE_PEAK   = "-1.5"
LRA         = "11"

HERE = os.path.dirname(os.path.abspath(__file__))
TEMP = os.path.join(HERE, "_temp_random_branch")
ITEMS = os.path.join(HERE, "items_random_branch.csv")


def words_from_page():
    """词表直接从试听页里读，保证与页面完全一致"""
    s = open(PAGE, encoding="utf-8").read()
    D = json.loads(re.search(r"const D=(\[.*?\]); let A", s, re.S).group(1))
    w = {y for x in D for y in (x["wa"], x["wb"])}
    return sorted(w)


def normalise(word):
    """两遍 EBU R128 响度归一化"""
    tp = os.path.join(TEMP, word + ".mp3")
    fp = os.path.join(HERE, word + ".mp3")
    if not os.path.exists(tp):
        return False
    meas = "loudnorm=I=%s:TP=%s:LRA=%s:print_format=json" % (TARGET_LUFS, TRUE_PEAK, LRA)
    r = subprocess.run(["ffmpeg", "-i", tp, "-af", meas, "-f", "null", "-"],
                       capture_output=True, text=True)
    s = r.stderr
    a, b = s.rfind("{"), s.rfind("}") + 1
    if a < 0 or b <= a:
        return False
    st = json.loads(s[a:b])
    apply_ = ("loudnorm=I=" + TARGET_LUFS + ":TP=" + TRUE_PEAK + ":LRA=" + LRA +
              ":measured_I=" + str(st["input_i"]) +
              ":measured_TP=" + str(st["input_tp"]) +
              ":measured_LRA=" + str(st["input_lra"]) +
              ":measured_thresh=" + str(st["input_thresh"]) +
              ":offset=" + str(st["target_offset"]) + ":linear=true")
    subprocess.run(["ffmpeg", "-y", "-i", tp, "-af", apply_,
                    "-codec:a", "libmp3lame", "-qscale:a", "2", fp], capture_output=True)
    return os.path.exists(fp)


async def main():
    try:
        v = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout
        print("ffmpeg: " + v.split("\n")[0])
    except FileNotFoundError:
        sys.exit("缺 ffmpeg：brew install ffmpeg")

    os.makedirs(TEMP, exist_ok=True)
    words = words_from_page()
    print("词表 %d 个，来自 items_random_branch.csv" % len(words))
    print("声音 %s，语速 %s，归一化 I=%s TP=%s LRA=%s\n" % (VOICE, RATE, TARGET_LUFS, TRUE_PEAK, LRA))

    bad = []
    for i, w in enumerate(words, 1):
        await edge_tts.Communicate(w, VOICE, rate=RATE).save(os.path.join(TEMP, w + ".mp3"))
        ok = normalise(w)
        if not ok:
            bad.append(w)
        print("  [%3d/%d] %-12s %s" % (i, len(words), w, "✓" if ok else "✗"))

    print("\n合成完毕，%d 个成功，%d 个失败%s" % (len(words) - len(bad), len(bad),
                                          ("：" + " ".join(bad)) if bad else ""))

    # ---- 响度自检 ----
    # 这些假词只有 0.6-1 秒，ffmpeg 的 loudnorm 对超短音频的测量在某些版本上会失准，
    # 归一化后可能整体偏轻十几 dB。逐个量一遍，偏离目标超过 1 dB 的列出来。
    print("\n逐个复核响度（目标 I = %s LUFS）……" % TARGET_LUFS)
    off = []
    for w in words:
        fp = os.path.join(HERE, w + ".mp3")
        if not os.path.exists(fp):
            continue
        r = subprocess.run(["ffmpeg", "-i", fp, "-af",
                            "loudnorm=I=%s:TP=%s:LRA=%s:print_format=json" % (TARGET_LUFS, TRUE_PEAK, LRA),
                            "-f", "null", "-"], capture_output=True, text=True)
        s2 = r.stderr
        a, b = s2.rfind("{"), s2.rfind("}") + 1
        if a < 0:
            off.append((w, None, None)); continue
        d = json.loads(s2[a:b])
        I, TP = float(d["input_i"]), float(d["input_tp"])
        if abs(I - float(TARGET_LUFS)) > 1.0:
            off.append((w, I, TP))
    if off:
        print("  ★ %d 个文件响度不对，别用这一版：" % len(off))
        for w, I, TP in off[:40]:
            print("      %-12s I=%s  TP=%s" % (w, ("%7.2f" % I) if I is not None else "  测不出",
                                               ("%6.2f" % TP) if TP is not None else "  --"))
        print("  ffmpeg 版本对短音频的 loudnorm 行为不一致是常见原因，换个版本再跑。")
    else:
        print("  全部 %d 个都在 %s ± 1 dB 以内 ✓" % (len(words), TARGET_LUFS))
    print("\n把 mp3 与 index.html 一起推到 GitHub")


if __name__ == "__main__":
    asyncio.run(main())
