# 不规则被试梳理（Irregular Subjects）

> 状态：调查 / 待决策文档。本文只做梳理与归类，**不修改任何数据**。
> 视角：以**原始 MATLAB 源码**为准，梳理它对不规则被试的处理；附录附上一份初步数据观察。
> 最后更新：2026-06。

---

## 0. 结论速览（TL;DR）

1. **MATLAB 里的 per-subject 修正只有一处枚举**：`bsliang_rpcode2trials.m` 的
   **`LexicalDecRepDelay`** 分支，硬编码了 8 个被试（D90 / D28 / D26 / D92 / D100 / D102 / D117 / D23）
   + 1 个路径特例（D63）。
2. **NoDelay 和 Uniqueness_Point 在 `rpcode2trials` 里一个 per-subject 修正都没有**——不是它们没问题，
   而是它们的问题在**更上游的触发提取**那一层，靠**人手**处理、**不写进代码**。
3. **UP / NoDelay 的真正麻烦 = 双触发（double triggers）**：见 `maketrigtimes.m`。每个试次发两个触发，
   原始检测会得到 ~960 个，必须**手动**砍半到 480，再**手动删**杂散触发。砍不干净 → `Trials.Auditory`
   与 `trialInfo`（每块 120 试次）错位 → 我们软件忠实复现这个坏对齐，`cue_events` 就乱了。
4. **因此「哪些 UP/NoDelay 被试有问题」在 MATLAB 源码里查不到**——源码没有这份名单。
   要得到它，只能**从每个被试的 `Trials.mat` 自身**去检测（见 §4），而不是查代码、也不是比对备份。

---

## 1. MATLAB 流程的两个修正层

response coding 之前，数据要先从 EDF 抽出触发、生成 `Trials.mat`。不规则修正散落在**两个层**：

```
EDF 原始触发
   │   ← 【层 A】触发提取  maketrigtimes.m
   │        · 双触发砍半 (UP / NoDelay)
   │        · 手动删杂散触发
   ▼
Trials.mat  (Trials.Auditory)  ──┐
trialInfo.mat (每块120试次)      ├─→ cue_events / condition_events  (make_cue_events_lr.m：无 per-subject 修正)
                                 │
MFA + 响应编码数组 ──────────────┘
   │   ← 【层 B】response coding  bsliang_rpcode2trials.m
   │        · per-subject 数组索引切片 (仅 LexicalDelay)
   │        · 刺激名重映射 / 路径特例
   ▼
写回 Trials.mat
```

- **层 A（上游，决定 `Trials.Auditory`）** —— UP / NoDelay 的问题在这里，**手动、无名单**。
- **层 B（response coding，决定响应/MFA 对齐）** —— Lexical**Delay** 的问题在这里，**有枚举名单**。

两层独立。某被试可能只在一层有问题，也可能两层都有。

---

## 2. 层 A：EDF→Trials.mat 触发预处理（UP / NoDelay 的核心问题）

> 本节是给「专门负责这部分的 agent」的交接材料：完整讲清触发预处理流程、双触发是什么、
> 它如何决定 `Trials.Auditory`、为什么脆弱、坏数据如何流到我们软件。

相关源码（在**我们软件的上游**，产出 `Trials.mat`；我们只读不写它）：

- `Response_Coding/coganlab_response_coding/retrocue/make_Trials_mat/ecog_preprocessing.m`（主脚本，EDF→Trials.mat）
- `…/make_Trials_mat/maketrigtimes.m`（从触发通道检测触发时刻）
- `…/make_Trials_mat/edfread_fast.m`、`plottrigtimes.m`、`write_experiment_file.m`

> 注：仓库里这份 `ecog_preprocessing.m` 是 **Retro Cue** 版（`subj_task='D123_012'` 等 case）。
> **触发检测机制对所有任务通用**；只是「每个试次打几个触发」「`Trials` 里填哪些字段」随任务不同。
> 实验室跑 UP/Lexical 时用的是结构相同、case 内容不同的另一份；本仓库未收录，但机制可照此理解。

### 2.0 流程总览

```
EDF 文件
  │  ① 抽出"触发通道"(DC1, 如第257号通道) → trigger.mat
  ▼
trigger  (一条平时为0、事件处拉高的方波信号)
  │  ② maketrigtimes.m: 阈值检测每个方波脉冲的起始 → trigTimes (一串触发时刻)
  ▼
trigTimes (≈960 for UP, 因双触发)
  │  ③ 【手动】trigTimes(1:2:end) 砍半 → 480;  trigTimes([...])=[] 删杂散
  ▼
trigTimes (期望 480 + 块起始触发)
  │  ④ ecog_preprocessing.m 循环: 一根游标顺序"消费"trigTimes, 填 Trials(A).Auditory/...
  ▼
Trials.mat  →  (我们的软件从这里开始)
```

### 2.1 触发通道是什么（① 抽通道）

EDF 记录里除了脑电通道，还有一条专门的**触发通道**（DC1，例：第 257 号通道）。
实验程序（PsychToolbox）每到一个事件节点，就往这条通道打一个**方波电压脉冲**（TTL）——
平时为 0，事件处"啪"地拉高。`ecog_preprocessing.m` 把它抽出来存成 `trigger.mat`：

```matlab
trigger = d(trigger_chan_index,:);   % trigger_chan_index 如 257 (DC1)
save('trigger', 'trigger');
```

### 2.2 `maketrigtimes.m`：脉冲 → 时刻（② 检测）

```matlab
thresh = 1.4e5;                              % 电压阈值 (除 Envelope Tracking 用 e4, 其余用 e5)
freq   = h.frequency(1);                     % 采样率
seconds_between_triggers = 0.5;              % "两个触发至少隔多久"——关键可调参数
num_samples_between_triggers = seconds_between_triggers * freq;

trigs = find(trigger >= thresh);             % 所有"高于阈值"的采样点
diff_trigs = diff(trigs);                    % 相邻高点之间的间隔
big_trigs  = find(diff_trigs > num_samples_between_triggers);  % "大间隔"=两个脉冲的分界
trigTimes  = [trigs(1) trigs(big_trigs+1)];  % 每个脉冲的"第一个采样点"=该触发起始时刻
```

一个脉冲是方波、会持续若干采样点（连成一片）；两个脉冲之间有大空档。
"找大空档右边那个点"= **每个脉冲的起始时刻**。`trigTimes` = 一串触发时刻（采样点单位）。
`plottrigtimes.m` 把检测结果叠在 trigger 波形上供肉眼核对。

### 2.3 "双触发"（double triggers）是什么（③ 手动砍半）

正常假设 = **一个事件一个脉冲**。但 **Uniqueness Point 每个试次打两个脉冲**
（注释明示「很可能 NoDelay 也是」）。于是 480 个试次 → 检测出 **≈960** 个 `trigTimes`。
要还原成"每试次一个"，操作者**手动**在 `maketrigtimes.m` 里敲（第 26–33 行）：

```matlab
%trigTimes = trigTimes(1:2:end); % to get rid of double triggers (alternate)
   % ^^ FOR UNIQUENESS POINT: Use 1 SECOND between so it doubles the total
       % (to 960), then run the double triggers alternate command above to cut down to 480!
   % ^^ Will also likely need to use it for Lexical No Delay
%trigTimes([1,2,3,etc.]) = []; % this one deletes specific trigs - KEY! (Pic Naming + GL others as needed)
```

- **A1 — 双触发砍半**：`trigTimes(1:2:end)`（隔一取一）把 960 → 480。
  配合调 `seconds_between_triggers`（注释里写 UP 用 1 秒）来控制成对脉冲是被"拆开计两个"还是"并成一个"。
  *（注：注释关于 1 秒/960 的措辞自相矛盾、像随手记的实验室笔记；以"双触发→隔一取一砍半"这个操作意图为准，别纠结那句话的字面算术。）*
- **A2 — 杂散触发删除**：`trigTimes([...]) = []` 按被试**手动**删掉阈值误捕的噪声脉冲（注释标「KEY!」）。

这两步都是操作者**逐被试、交互式、肉眼看波形**做的，**完全不入代码**——所以源码里找不到"哪些被试做了什么"的记录。

### 2.4 `trigTimes` → `Trials.Auditory`（④ 顺序消费）

`ecog_preprocessing.m` 的主循环（第 186–241 行）用**一根游标 `trigT_idx` 顺序往下走**，
逐块、逐试次"消费"`trigTimes`，填进 `Trials`。简化版（Retro Cue 字段，UP/Lexical 类似但字段名为 `Auditory` 等）：

```matlab
trigT_idx = 0;
for A = 1:numel(trialInfo)
    % 每个块的第一条试次: 先吃掉一个"块起始"触发
    if A==1 || trialInfo(A).block ~= trialInfo(A-1).block
        trigT_idx = trigT_idx + 1;
        Rec_onsets(end+1) = floor(trigTimes(trigT_idx) * 30000 / freq);
    end
    % 然后按顺序吃掉该试次的各个触发
    trigT_idx = trigT_idx + 1;
    Trials(A).audio1Start = floor(trigTimes(trigT_idx) * 30000 / freq);  % UP/Lexical: Trials(A).Auditory
    trigT_idx = trigT_idx + 1;
    Trials(A).audio2Start = floor(trigTimes(trigT_idx) * 30000 / freq);
    ...
end
```

关键点：**游标是顺序、不可回头的**。`trigTimes` 的第 k 个必须恰好是"第某试次的某事件"。
（`* 30000 / freq` 是把采样点换算到 30kHz 统一时基。）

### 2.5 为什么脆弱 / 为什么"从某试次起整段乱掉"

如果某个试次**少打一个脉冲 / 多一个噪声脉冲 / 双触发没整齐成对**，
那么 `trigTimes(1:2:end)` 的隔一取一就从那一点**错位一格**，
之后**所有**试次的触发整体平移 → `Trials.Auditory` 与 `trialInfo` 的"第 t 试次"全部对不上
→ 块边界对不齐 → 我们的 `cue_events` 忠实复现这个错位。

这正是 **D86 / D90** 的现象：前段正常，从某试次起整段错乱，错位量 ≈ 一两个试次时长（4~12s），
正是"多/少一个触发"的尺度。**我们软件不是 bug——它只是把上游已经错了的 `Trials.Auditory` 算进了 cue_events。**

### 2.6 其实有道内置对齐检查（但靠人跑）

`ecog_preprocessing.m` 第 218–226 行有一道防线：拿 `Trials` 里两个触发的间隔 vs `trialInfo` 里记录的
间隔比，差 **≥10ms 就 `error('Auditory gap not matched with trialInfo')`**：

```matlab
Aud_onset_diff_from_trialInfo = trialInfo(A).audio2Start - trialInfo(A).audio1Start;
Aud_onset_diff_from_Trials    = (Trials(A).audio2Start - Trials(A).audio1Start)/3e4;
if abs(Aud_onset_diff_from_trialInfo - Aud_onset_diff_from_Trials) >= 0.01
    error('Auditory gap not matched with trialInfo')
end
```

双触发砍歪了，这道检查**理应**拦下来。坏数据仍流到下游，说明 UP 当年的脚本要么没保留这道检查、
要么被操作者跳过/注释掉了。**这是一个值得在我们软件里复刻的安全网**（见 §5）。

### 2.7 小结

> UP/NoDelay 每个试次打**两个**触发 → 检测出 ≈960 个 → 人手 `(1:2:end)` 砍半到 480 + 手删杂散。
> 只要有一处双触发没成对，隔一取一就从那里开始错位，后面整段崩。
> 这一步全在我们软件**上游**、且**不入代码**，坏数据被 bake 进 `Trials.mat` 传给我们。
> Delay 任务是单触发，基本不踩这个坑——所以层 A 的问题集中在 **UP 和 NoDelay**。

---

## 3. 层 B：response coding 的 per-subject 修正（仅 LexicalDelay 有枚举）

来源：`references/lexical/bsliang_rpcode2trials.m`（与 lab 原版逐字节一致）。
这些修正把 MFA/响应数组（`StimStart_mfa / StimEnd_mfa / StimCue / ResponseStart / ResponseEnd`）
切片，使之与 `trialInfo` 对齐——**全部 gated 在 `if strcmp(task_type,"LexicalDecRepDelay")` 之下**。

| 行 | 被试 | 修正 | 类型 |
|---|---|---|---|
| 100 | **D90** | `ResponseStart = ResponseStart(1:296)` | 截尾（删末尾多余） |
| 102 | **D28** | 所有 MFA 数组 `[1:299, 314:end]` | 删中段（删第 300–313，共 14 个） |
| 108 | **D26** | 所有 MFA 数组 `(169:end)` | 删头（删前 168） |
| 114 | **D92** | 所有 MFA 数组 `(85:end)` | 删头（删前 84） |
| 120 | **D100** | `ResponseStart(1:252)` | 截尾 |
| 122 | **D102** | `ResponseStart(1:331)` | 截尾 |
| 124 | **D117** | 所有 MFA 数组 `[1:113, 115:end]` | 删单个（删第 114） |
| 206 | **D23** | `casif.wav→casef.wav`、`valek.wav→valuk.wav` | 刺激名重映射 |

另：`make_condition_events.m:12` 的 **D63** —— 数据不在标准路径，硬写了路径分支（路径特例）。

**`NoDelay` 分支（136–179 行）：无任何 per-subject 修正。`Uniqueness_Point`：脚本里不按名出现。**

> 重要：层 B 的切片**只修响应/MFA 数组、不修 `cue_events`**。`make_cue_events_lr.m` 里没有任何 per-subject 分支。
> 那备份里坏被试的 `cue_events` 当年是怎么变好的？——`make_condition_events.m` 开头注释泄底：
> *"Usually I did not regenerate the condition_event after correcting the cue_event…"* ——
> 说明 **`cue_events` 是人在 Audacity 里手工改好的**。这给了我们一条思路：用我们自己的编辑器手改，而非硬编码。

---

## 4. 各种问题的分类（汇总）

| 类型 | 所在层 | 现象 | MATLAB 处理 | 涉及任务 | 已枚举？ |
|---|---|---|---|---|---|
| **A1 双触发** | 触发提取 | 触发数≈960，需砍半到480；砍不齐→整体错位 | 手动 `trigTimes(1:2:end)` | **UP / NoDelay** | ✗ 手动无名单 |
| **A2 杂散触发** | 触发提取 | 阈值误捕噪声→触发数≠480 / 错位 | 手动 `trigTimes([...])=[]` | 任意（UP/NoDelay 高发） | ✗ 手动无名单 |
| **B1 截尾** | response coding | 末尾多出试次 | `(1:N)` | LexicalDelay | ✓ D90/D100/D102 |
| **B2 删头** | response coding | 开头多出试次（中断重开的废run） | `(K:end)` | LexicalDelay | ✓ D26/D92 |
| **B3 删中段** | response coding | 中间多出一段试次 | `[1:a, b:end]` | LexicalDelay | ✓ D28 |
| **B4 删单个** | response coding | 单个杂散试次 | `[1:k-1, k+1:end]` | LexicalDelay | ✓ D117 |
| **C trialInfo 结构** | trialInfo | 分块存/末尾残块 | combine + fix_blocks（D140 类） | 任意 | 部分（我们已实现） |
| **D 标注/路径一次性** | 杂项 | 刺激名笔误 / 数据非标准路径 | 重映射(D23) / 路径覆盖(D63) | LexicalDelay | ✓ |

**给 UP / NoDelay 的结论**：它们的问题几乎都落在 **A1/A2（触发层）**，而这层 **MATLAB 没有枚举名单**。
层 B 的那串 D 号是 **LexicalDelay 专属**，不能照搬到 UP/NoDelay。

---

## 5. 这对我们软件意味着什么 + 后续怎么改（待讨论）

我们的软件把 `Trials.mat` 当**外部输入**直接读 `Trials.Auditory`——也就是说**层 A 的坏数据是从上游 bake 进来的**，
我们正常路径只会忠实复现。要解决 UP/NoDelay 的不规则，候选方向：

1. **先搞清楚「哪些 UP 被试有问题」——只能从数据检测，不能查代码。**
   既然 MATLAB 没名单，备份又因当前只跑到 D90 不能当全标准，那就**逐被试体检 `Trials.mat` 自身**：
   - `len(Trials.Auditory) == len(trialInfo) == 480`？
   - 大的 Auditory 间隔（块间停顿）是否正好落在 trialInfo 的 120/240/360 块边界上？
   - 有没有**双触发残留**（相邻 Auditory 间隔异常小，成对出现）？
   - 有没有**整试次级跳变**（块内出现 ≈单试次时长 4~12s 的异常间隔）？
   - **（最权威）复刻 §2.6 的对齐检查**：若 `trialInfo` 里记了试次内事件间隔（如 audio1→audio2），
     就拿 `Trials` 里同样的间隔逐试次比，差 ≥10ms 即判该试次起错位。这是 MATLAB 自带安全网的直接移植。
   → 这套检测**不依赖备份、不依赖我们是否已处理**，是回答「谁有问题」的正道。
   （注意：`D_Data` 里很多 `Trials.mat` 是 Box 云占位、没下载，能体检的只有已下载的那些。）

2. **在软件里内置「不规则自动检测 + FLAG」**：把上面的体检做成处理前的自动检查，
   触发数不对/块边界对不齐就把被试标 **FLAGGED**，提醒人工核对，避免坏数据悄悄流到下游。

3. **修正方式二选一或结合**：
   - **(a) 编辑器手工修**（沿用老流程「手改 cue_events」思路，最灵活，适合层 A 的逐试次错位）；
   - **(b) 数据驱动修正表** `corrections.yaml`（适合层 B 那种规整的索引切片；UP 的具体规则需逐被试确定）。

**需要你定的关键问题：**
- **Q1**：UP/NoDelay 被试的「正确触发/对齐」事实从哪来？是否有人保留过当年手动清洗触发的记录（删了哪些、怎么砍的）？
  若没有，就只能靠 §5.1 的数据体检 + 人工在编辑器里核对重建。
- **Q2**：长期路线选 (a) 编辑器手工、(b) 修正表、还是「先自动 FLAG，再按需手改」？
- **Q3**：要不要我现在就跑一遍 §5.1 的 `Trials.mat` 体检（对已下载的 UP 被试），先拿到一份「疑似有问题」清单？

---

## 附录 A：初步数据观察（仅供参考，不作为标准）

> ⚠️ 当前结果目录只处理到 D90、并不完整，所以下表**不能**当作权威名单；仅作为「数据体检」思路的预演。

用「当前结果 vs 备份 `cue_events`」（去每块常数偏移后看残差）对已处理被试做过一次对比，发现 4 个明显分叉：

| 被试 | 现象 | 推测（层 A） |
|---|---|---|
| **D86** | block1 第7试次起偏+4s，block3 尾部 **+662s**，整段错乱 | 触发严重错位/缺失 |
| **D90** | block1 第67试次起 −4.5s；block2/3 各突跳 +12s；block4 干净 | 多处整试次级触发错位 |
| **D42** | block2 第123试次一个 +0.8s 台阶 | 局部触发错位 |
| **D28** | 每块内 ~1s 缓慢漂移、过块复位（最轻） | 更像 Trials.mat 重抽取微差，未必需修 |

这与 §2 的双触发机制吻合（整试次级 4~12s 跳变 = 触发多/少一两个）。但**权威清单要等 §5.1 的逐被试 `Trials.mat` 体检**。

---

## 附：相关文件

- `Response_Coding/coganlab_response_coding/retrocue/make_Trials_mat/maketrigtimes.m`（层 A：双触发/手动删触发）
- `references/lexical/bsliang_rpcode2trials.m`（层 B：LexicalDelay per-subject 切片 + D23 重映射）
- `references/lexical/make_cue_events_lr.m`（无 per-subject 分支 → `core/events/cue_events.py`）
- `references/lexical/make_condition_events.m`（D63 路径特例 + 「cue_events 手工修」的注释线索）
- `references/response_coding_dep/{combine_trialInfo,fix_trialInfo_blocks}.m`（层 C：trialInfo 结构）
- 数据位置：
  - 当前结果：`…/response_coding/response_coding_results/Uniqueness_Point/<subj>/`（仅处理到 D90）
  - 好备份：`G:\CoganLabData\RPCoding_backup\Uniqueness_Point/<subj>/`（仅结果，无 `Trials.mat`）
  - 源 `Trials.mat`：`…/CoganLab/D_Data/Uniqueness_Point/<subj>/<date>/mat/Trials.mat`
