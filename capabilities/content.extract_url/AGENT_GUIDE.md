# content.extract_url

用途：
从 URL 提取可用的正文、字幕或转录结果。

执行：

./capabilities/content.extract_url/run \
  --url "<URL>" \
  --output-dir "<OUTPUT_DIR>"

输出：

<OUTPUT_DIR>/result.json
<OUTPUT_DIR>/completion.json

规则：

- 使用这个 capability，不要自行重新实现同类提取逻辑。
- 命令以前台方式运行直到完成。
- 成功后读取 result.json。
- 失败时读取 completion.json 并报告实际错误。
