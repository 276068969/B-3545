# 问题记录 — 个人主页高光收藏展示卡

## 基本信息
- **功能模块**: 个人主页 - 高光收藏展示卡
- **发现日期**: 2026-06-08
- **状态**: 已修复

---

## 问题 1：「本人参与」被错误实现为「本人获胜」

### 问题描述
需求中「本人参与的精彩对局」是指用户作为玩家参与过的游戏中的高光时刻，但实现时错误地使用了 `winner=profile_user` 筛选条件，只返回了用户作为获胜者的高光。

### 严重程度
高

### 根本原因
对需求理解偏差，将「参与」等同于「获胜」。`Highlight` 模型有 `winner` 字段（高光主角/赢家），但「本人参与」应指用户出现在游戏的玩家列表中，即 `game.players` 包含该用户。

### 影响范围
- 个人主页「精彩对局」区块展示的数据不准确
- 查看他人主页时看到的高光数量偏少
- 用户作为输家或其他名次参与的精彩对局无法展示

### 修复方案
**修改文件**: `apps/accounts/views.py`

修改前:
```python
user_highlights = Highlight.objects.filter(
    winner=profile_user
).select_related(
    'game'
).prefetch_related(
    'game__players__user'
).order_by('-is_pinned', '-is_featured', '-highlight_score', '-created_at')[:4]
```

修改后:
```python
user_highlights = Highlight.objects.filter(
    game__players__user=profile_user
).select_related(
    'game', 'winner'
).prefetch_related(
    'game__players__user'
).order_by('-is_pinned', '-is_featured', '-highlight_score', '-created_at').distinct()[:4]
```

**关键改动**:
1. 筛选条件从 `winner=profile_user` 改为 `game__players__user=profile_user`
2. 添加 `.distinct()` 去重（跨表 join 可能产生重复行）
3. `select_related` 增加 `winner` 字段预加载

---

## 问题 2：高光时刻区块不显示 / 展示数据偏少

### 问题描述
不同账号打开个人主页时，「高光时刻」区块经常不显示，或展示的数据量明显偏少。

### 严重程度
高

### 根本原因
由问题 1 间接导致。由于只筛选用户作为获胜者的高光，如果用户赢的局数少或没有产生高光的赢局，`user_highlights` 就为空。再加上查看他人主页时 `collected_highlights` 为空列表，两个条件都不满足，整个区块就不渲染。

### 影响范围
- 大部分用户的个人主页看不到高光时刻区块
- 功能使用率低，用户无法从个人主页回看精彩内容

### 修复方案
同问题 1 的修复。将筛选范围扩大为「参与过的游戏」后，高光数量显著增加，区块显示概率大幅提升。

---

## 问题 3：「查看全部」链接筛选参数无效

### 问题描述
高光展示卡右上角的「查看全部」链接使用了 `?winner={{ profile_user.pk }}` 参数，但高光集锦页（`/leaderboard/highlights/`）并未实现 `winner` 和 `player` 参数的筛选逻辑，点击后显示的是全部高光。

### 严重程度
中

### 根本原因
`leaderboard/views.py` 中的 `highlights_board` 视图只实现了 `type` 和 `sort` 参数，缺少 `winner` 和 `player` 筛选。

### 影响范围
- 「查看全部」链接跳转后未按用户筛选，用户体验不一致
- 无法从个人主页快速跳转到该用户相关的全部高光

### 修复方案
**修改文件**: `apps/leaderboard/views.py`

在 `highlights_board` 函数中新增筛选逻辑:
```python
winner_filter = request.GET.get('winner', '')
player_filter = request.GET.get('player', '')

# ...

if winner_filter:
    highlights_qs = highlights_qs.filter(winner_id=winner_filter)

if player_filter:
    highlights_qs = highlights_qs.filter(game__players__user_id=player_filter).distinct()
```

同时更新模板中的链接参数:
- 从 `?winner={{ profile_user.pk }}` 改为 `?player={{ profile_user.pk }}`
- 与「本人参与」的语义保持一致

---

## 修复验证清单

- [x] `user_highlights` 查询使用 `game__players__user` 替代 `winner`
- [x] 添加 `.distinct()` 防止重复数据
- [x] `select_related` 包含 `winner` 字段
- [x] `highlights_board` 支持 `winner` 和 `player` 筛选参数
- [x] 「查看全部」链接使用 `player` 参数
- [x] 区块显示条件正确（有收藏或有参与高光时显示）
- [x] 本人主页同时显示「我的收藏」和「精彩对局」
- [x] 他人主页只显示「精彩对局」

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `apps/accounts/views.py` | 修正 user_highlights 查询逻辑 |
| `templates/accounts/profile.html` | 修正「查看全部」链接参数 |
| `apps/leaderboard/views.py` | 新增 winner 和 player 筛选支持 |
