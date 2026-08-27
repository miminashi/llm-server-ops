import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.font_manager as fm

fm.fontManager.addfont('/usr/share/fonts/truetype/fonts-japanese-gothic.ttf')
plt.rcParams['font.family'] = 'IPAGothic'
plt.rcParams['axes.unicode_minus'] = False

SURFACE   = '#fcfcfb'
TEXT      = '#0b0b0b'
TEXT2     = '#52514e'
USED      = '#2a78d6'   # categorical slot 1
TRACK     = '#e3e2dd'

# 実測値 (2026-08-27 23:47 JST, 起動成功後)
labels = ['CUDA0','CUDA1','CUDA2','CUDA3','CUDA4','CUDA5','CUDA6',
          'RPC0','RPC1','RPC2','RPC3','RPC4','RPC5']
used   = [14672,14672,11294,14672,14672,14672, 4884,
           5402,14672,15806,11152,11288,11296]
cap    = [16384,16384,16384,16384,16384,16384,16384,
          16384,16384,16384,12288,16384,12288]

y = list(range(len(labels)))[::-1]

fig, ax = plt.subplots(figsize=(9.4, 6.2), dpi=170)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)

ax.barh(y, cap,  height=0.62, color=TRACK, zorder=2)
ax.barh(y, used, height=0.62, color=USED,  zorder=3)

for yi, u, c in zip(y, used, cap):
    ax.text(17100, yi, f'空き {c-u:,} MiB', va='center', ha='left',
            fontsize=8.4, color=TEXT2, zorder=4)
    ax.text(u - 260, yi, f'{u:,}', va='center', ha='right',
            fontsize=8.4, color=SURFACE, zorder=5)

ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=9.4, color=TEXT)
ax.set_xlim(0, 21600)
ax.set_xticks([0,4096,8192,12288,16384])
ax.set_xticklabels(['0','4,096','8,192','12,288','16,384'], fontsize=9, color=TEXT2)
ax.set_xlabel('VRAM (MiB)', fontsize=9.6, color=TEXT2, labelpad=8)
ax.xaxis.grid(True, color='#eceae4', linewidth=1, zorder=1)
ax.set_axisbelow(True)
for s in ('top','right','left'): ax.spines[s].set_visible(False)
ax.spines['bottom'].set_color('#d8d7d2')
ax.tick_params(length=0)

fig.text(0.012, 0.965, 'GLM-5.3-Flash UD-IQ4_XS — 13 GPU への VRAM 配分（起動成功時）',
         fontsize=12.6, color=TEXT, ha='left', va='top')
fig.text(0.012, 0.918,
         'CUDA0–6 = aws-gpu01 / RPC0–5 = aws-gpu02（RPC3・RPC5 のみ 12 GB 版）   ctx=32768, -ub 64, -fa off',
         fontsize=8.8, color=TEXT2, ha='left', va='top')

ax.legend(handles=[Patch(facecolor=USED, label='使用中'),
                   Patch(facecolor=TRACK, label='搭載容量')],
          loc='lower right', frameon=False, fontsize=9, labelcolor=TEXT2)

fig.tight_layout(rect=[0,0,1,0.90])
out='report/attachment/2026-08-27_235754_glm53flash_aws_gpu_rpc_startup/vram_allocation.png'
fig.savefig(out, facecolor=SURFACE)
print('saved', out, 'total used =', sum(used), 'MiB')
