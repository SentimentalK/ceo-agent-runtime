#!/usr/bin/env python3
"""
Bilibili 语法系列全套视频字幕批量提取脚本
- 从 B站 UGC Season API 获取 BV1jF411r73p 合集全 28 集列表
- 使用 yt-dlp --skip-download 搭配 Chrome Cookies 提取字幕
- 自动转换生成 .srt 文件和纯文本 .txt 文件
"""

import os
import re
import json
import ssl
import subprocess
import urllib.request

# 解决 SSL 证书错误
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

START_BVID = "BV1jF411r73p"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subtitles")
YT_DLP_PATH = "/Library/Frameworks/Python.framework/Versions/3.12/bin/yt-dlp"

def sanitize_filename(name):
    # 替换文件名非法字符
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    name = name.replace(' ', '_').replace('\t', '_')
    return name.strip('_')

def fetch_ugc_episodes(bvid):
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
    
    with urllib.request.urlopen(req, context=ctx) as resp:
        data = json.loads(resp.read().decode()).get('data', {})
        
    ugc_season = data.get('ugc_season', {})
    sections = ugc_season.get('sections', [])
    
    episodes = []
    if sections:
        for sec in sections:
            for ep in sec.get('episodes', []):
                episodes.append({
                    'bvid': ep.get('bvid'),
                    'title': ep.get('title') or ep.get('arc', {}).get('title', 'Unknown'),
                    'cid': ep.get('cid')
                })
    else:
        # 如果不是合集，单集退回
        episodes.append({
            'bvid': bvid,
            'title': data.get('title', 'Unknown'),
            'cid': data.get('cid')
        })
        
    return episodes

def srt_to_txt(srt_path, txt_path):
    """将 SRT 字幕转写为干净无视时间戳的纯文本文件"""
    if not os.path.exists(srt_path):
        return False
        
    with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    # 按空行分割字幕块
    blocks = content.strip().split('\n\n')
    text_lines = []
    for block in blocks:
        block_lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(block_lines) >= 3:
            # 第一行数字，第二行时间戳，第三行及以后是文本
            sub_text = ' '.join(block_lines[2:])
            if sub_text and (not text_lines or text_lines[-1] != sub_text):
                text_lines.append(sub_text)
        elif len(block_lines) == 2 and '-->' in block_lines[0]:
            sub_text = block_lines[1]
            if sub_text and (not text_lines or text_lines[-1] != sub_text):
                text_lines.append(sub_text)

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text_lines))
        
    return True

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"正在从 B站 API 获取合集列表 (起始 BV: {START_BVID})...")
    
    episodes = fetch_ugc_episodes(START_BVID)
    total = len(episodes)
    print(f"成功找到 {total} 集视频！开始获取字幕...\n")
    
    success_count = 0
    
    for idx, ep in enumerate(episodes, 1):
        bvid = ep['bvid']
        raw_title = ep['title']
        clean_title = sanitize_filename(raw_title)
        prefix = f"{idx:02d}"
        base_name = f"{prefix}_{clean_title}"
        
        print(f"[{idx}/{total}] 处理中: {raw_title} ({bvid})")
        
        url = f"https://www.bilibili.com/video/{bvid}"
        target_template = os.path.join(OUTPUT_DIR, f"{base_name}.%(ext)s")
        
        # yt-dlp 命令提取字幕
        cmd = [
            YT_DLP_PATH,
            "--cookies-from-browser", "chrome",
            "--skip-download",
            "--write-sub",
            "--write-auto-sub",
            "--sub-lang", "ai-zh,zh-Hans,zh-CN,zh,all",
            "-o", target_template,
            url
        ]
        
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        # 查找生成的字幕文件 (.srt / .vtt)
        found_sub = None
        for ext in ['.ai-zh.srt', '.zh-Hans.srt', '.zh-CN.srt', '.zh.srt', '.srt', '.vtt']:
            possible_path = os.path.join(OUTPUT_DIR, f"{base_name}{ext}")
            if os.path.exists(possible_path):
                found_sub = possible_path
                break
                
        # 兜底查找该前缀下的任何 .srt / .vtt
        if not found_sub:
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith(prefix) and (f.endswith('.srt') or f.endswith('.vtt')):
                    found_sub = os.path.join(OUTPUT_DIR, f)
                    break
                    
        if found_sub:
            # 规范重命名 SRT 路径
            final_srt = os.path.join(OUTPUT_DIR, f"{base_name}.srt")
            if found_sub != final_srt:
                os.rename(found_sub, final_srt)
            
            # 转码出纯文本 txt
            final_txt = os.path.join(OUTPUT_DIR, f"{base_name}.txt")
            srt_to_txt(final_srt, final_txt)
            
            print(f"  └─ SUCCESS: 字幕文件已保存至 {base_name}.srt 和 {base_name}.txt")
            success_count += 1
        else:
            print(f"  └─ WARNING: 未检测到 {bvid} 的字幕")
            
    print(f"\n全部处理完毕！成功下载并转换 {success_count}/{total} 集字幕。")
    print(f"字幕保存位置: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
