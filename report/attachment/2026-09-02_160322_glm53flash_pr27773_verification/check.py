import json, sys, re, collections
path = sys.argv[1]
codes = sys.argv[2:]
d = json.load(open(path))
if 'choices' not in d:
    print('ERROR:', json.dumps(d)[:300]); sys.exit(1)
ch = d['choices'][0]; m = ch['message']
c = m.get('content') or ''
rc = m.get('reasoning_content') or ''
print('CONTENT:', repr(c[:250]))
for code in codes:
    print(f'  {code}: {"OK" if code in c else "MISS"}')
print('THINK_LEN:', len(rc), 'finish:', ch.get('finish_reason'))
# depth collapse 検出: 同一文字の 20 連以上、または同一 4-gram の 15 回以上反復
allt = c + rc
run = max((len(x) for x in re.findall(r'(.)\1{4,}', allt) and [mm.group(0) for mm in re.finditer(r'(.)\1{4,}', allt)]), default=0)
grams = collections.Counter(allt[i:i+4] for i in range(max(0, len(allt)-3)))
top = grams.most_common(1)[0] if grams else ('', 0)
print('COLLAPSE: max_char_run=', run, ' top4gram=', repr(top[0]), top[1])
t = d.get('timings', {})
print('pp:', round(t.get('prompt_per_second', 0), 1), 'tg:', round(t.get('predicted_per_second', 0), 1),
      'n_prompt:', t.get('prompt_n'), 'n_pred:', t.get('predicted_n'))
