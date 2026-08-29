"""GLM-5.3-Flash 対応 PR 2 本の起動可否と prompt 処理速度。
横棒 = 起動できた構成の pp t/s。起動できなかった構成は棒を描かず、
確保に失敗したバッファサイズを直接ラベルする（成功/失敗が形で読める）。
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.font_manager as fm

fm.fontManager.addfont('/usr/share/fonts/truetype/fonts-japanese-gothic.ttf')
plt.rcParams['font.family'] = 'IPAGothic'
plt.rcParams['axes.unicode_minus'] = False

SURFACE = '#fcfcfb'
TEXT    = '#0b0b0b'
TEXT2   = '#52514e'
S1      = '#2a78d6'   # categorical slot 1: #27754 (unsloth)
S2      = '#eb6834'   # categorical slot 2: #27752 (eauchs)
FAILC   = '#b9b7ae'   # 失敗はニュートラル（系列色を使わない）

# (ラベル, PR, pp t/s or None=起動失敗, 補足)
rows = [
    ('ctx 32k / ub 64 / -fa off',  '27754',  None, '2 slot 同時でも両方正解'),
    ('ctx 32k / ub 512 / -fa on',  '27754',  57.9, ''),
    ('ctx 32k / ub 1024 / -fa on', '27754',  67.9, 'graph_reserve 失敗も継続'),
    ('ctx 256k / ub 64 / -fa on',  '27754',  14.3, ''),
    ('ctx 32k / ub 64 / -fa off',  '27752',  None, '単体は正解／2 slot 同時で劣化'),
    ('ctx 32k / ub 512 / -fa on',  '27752',  None, '起動失敗 1.60 GiB'),
    ('ctx 32k / ub 1024 / -fa on', '27752',  None, '起動失敗 3.20 GiB'),
    ('ctx 32k / ub 2048 / -fa on', '27752',  None, '起動失敗 4.39 GiB'),
    ('ctx 32k / ub 4096 / -fa on', '27752',  None, '起動失敗 6.78 GiB'),
]
# 起動できた ub 64 構成には速度実測がないので、棒は描かず OK とだけ示す
OK_NO_SPEED = {0, 4}

y = list(range(len(rows)))[::-1]
fig, ax = plt.subplots(figsize=(11.2, 6.4), dpi=170)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)

XMAX = 104
for yi, (lab, pr, v, note) in zip(y, rows):
    c = S1 if pr == '27754' else S2
    idx = rows.index((lab, pr, v, note))
    if v is not None:
        ax.barh(yi, v, height=0.58, color=c, zorder=3)
        ax.text(v + 1.4, yi, f'{v:.1f} t/s', va='center', ha='left',
                fontsize=9.6, color=TEXT, zorder=4)
        if note:
            ax.text(v + 13.5, yi, note, va='center', ha='left',
                    fontsize=8.2, color=TEXT2, zorder=4)
    else:
        mark = '起動 OK' if idx in OK_NO_SPEED else '起動できず'
        col  = c if idx in OK_NO_SPEED else FAILC
        ax.barh(yi, 1.1, height=0.58, color=col, zorder=3)   # 存在を示す極小マーク
        ax.text(3.2, yi, mark, va='center', ha='left', fontsize=9.2,
                color=TEXT if idx in OK_NO_SPEED else TEXT2, zorder=4)
        if note:
            ax.text(15.0, yi, note, va='center', ha='left',
                    fontsize=8.2, color=TEXT2, zorder=4)

ax.set_yticks(y)
ax.set_yticklabels([r[0] for r in rows], fontsize=9.4, color=TEXT)
ax.set_xlim(0, XMAX); ax.set_ylim(-0.8, len(rows) - 0.2)
ax.set_xlabel('プロンプト処理速度 (t/s, 約 11k トークン入力)', fontsize=9.6, color=TEXT2)

# PR ごとの区切り
ax.axhline(4.5, color='#d8d6ce', lw=1.0, zorder=1)
ax.text(XMAX - 0.5, 7.75, 'PR #27754 (unsloth)', ha='right', fontsize=10.2, color=S1, weight='bold')
ax.text(XMAX - 0.5, 3.75, 'PR #27752 (eauchs)',  ha='right', fontsize=10.2, color=S2, weight='bold')

for s in ('top', 'right', 'left'):
    ax.spines[s].set_visible(False)
ax.spines['bottom'].set_color('#d8d6ce')
ax.tick_params(axis='x', colors=TEXT2, labelsize=9)
ax.tick_params(axis='y', length=0)
ax.grid(axis='x', color='#eceae3', lw=0.8, zorder=0)
ax.set_axisbelow(True)

ax.legend(handles=[Patch(facecolor=S1, label='#27754 で起動できた構成'),
                   Patch(facecolor=S2, label='#27752 で起動できた構成'),
                   Patch(facecolor=FAILC, label='起動できなかった構成')],
          loc='lower right', frameon=False, fontsize=9, ncol=1,
          bbox_to_anchor=(1.0, -0.005))

ax.set_title('同じ 13 GPU 構成でも、通る -ub は PR によって 16 倍違う',
             fontsize=13, color=TEXT, pad=14, loc='left', weight='bold')
fig.text(0.125, 0.925, 'aws-gpu01 + aws-gpu02 / GLM-5.3-Flash UD-IQ4_XS 146 GiB / RPC 分散 13 GPU・200 GiB',
         fontsize=8.8, color=TEXT2, ha='left')

fig.tight_layout(rect=[0, 0, 1, 0.94])
fig.savefig('startup_matrix.png', facecolor=SURFACE)
print('wrote startup_matrix.png')
