# 澄岸测绘等值线交班

白班登记高程并固定调查口径，调度员逐幅交付等值证据，夜班断开高程源后按所选幅复核连通性，后班凭原号核账。需要 Python 3.11，依赖均来自标准库。以下命令从项目根目录运行。

```sh
python3.11 -B verify.py
python3.11 -B demo.py
```

演示在临时目录创建源库、调查目录、幅件库和报告台账。它对同一调查先后签发两幅，登记高程更正并移开源库。夜班复核只选左幅和左右全选两种覆盖。手算样例中左幅有两片，左幅底边所属片经共边的 1/3 处接到右幅底边。两个报告都含两组，全选报告恰有一组跨两格。重开后按两个报告号分别核对领件结果。

## 登记与开单

- `grid.revisions.RevisionStore(path)` 和 `survey.catalog.SurveyCatalog(path)` 分别持有源库和可交班的调查目录。调用 `grid.intake.initialize_grid(source)` 与 `surveys.initialize()` 建表。初始化可重复执行并保留已有数据。
- `grid.intake.register_grid(source, grid_id, origin, spacing, elevations)` 返回修订号。原点和轴距依次为 X、Y，单位为米，轴距为正。高程矩阵至少有两行两列且完整。行从南向北增长，列从西向东增长。高程、原点及轴距可用整数、`Fraction` 或有理数字符串表示。零是合法高程。用相同网格号登记更正会得到新修订。
- `grid.intake.read_grid_revision(source, revision_id)` 读取固定几何与样本。`survey.register.open_survey(source, surveys, revision_id, level, ranges)` 返回固定调查对象，包含 `survey_id` 和布局。高程与等值高程使用同一垂直基准和单位。`ranges` 把幅号映射到 `(row_start, col_start, row_stop, col_stop)`。末端不含在覆盖内。各幅原格互斥，可以留空、共边或共角。`surveys.read(survey_id)` 可读取当时绑定的修订、口径、几何及幅目录。

## 签发及交班

- `sheet.store.SheetStore(path)` 的 `initialize()` 建立幅件库。`sheet.publish.publish_sheet(source, surveys, sheets, survey_id, sheet_id)` 按调查固定的高程修订加工单幅，提交包和回执后返回 `packet_id` 和 `receipt`。`sheet.store.read_sheet(sheets, packet_id)` 返回原存 JSON 文本，`sheets.read_receipt(packet_id)` 领取其成功回执。
- 所有局部片都由格内双线性等值集定义。四边各有交点时按实际支路归属分片，鞍点恰等值时相交支路同片。整条等值边、整格等值和孤立角点均保留。V1 包包含 `version`、`survey_id`、`sheet_id`、`packet_id`、`coverage` 和 `components`。覆盖沿用开单范围。每片包含 `cell`、`part` 和 `contacts`。`cell` 是原格行、列，`part` 是格内非负整数标识。每个接触有 `start` 和 `end`，均为原空间 `(x,y)`，每个有理值编码为 `[分子, 正分母]`。两端相同表示点，否则表示轴对齐闭段。格角的点只需记录一次。合法空幅的 `components` 为空。
- 夜班用同一个固定调查目录和选中的原封包工作。`ledger.catalog.ReportCatalog(path)` 的 `initialize()` 建表。`review.assemble.issue_review(surveys, reports, survey_id, selected_sheet_ids, packets)` 接收幅号和对应 JSON 文本的可迭代对象。每个所选幅恰好交一个包。缺包、多交、重复幅、混单和结构无效的包均拒绝。交班输入由固定调查目录和包构成，复核入口不需要源库或幅件库。
- 复核连接共同空间位置上相交的闭接触，支持分数接点、共角及闭段。每个片恰属一组，接触链可传递，未选择的幅不参与。同覆盖重切幅和反序交件的归组一致，采用清单仍反映各次签发。`issue_review` 返回 `report_id` 和 `receipt`。`ledger.history.read_review(reports, report_id)` 返回持久归组、采用幅件及该报告对应的回执。空等值集是可签发的空组报告。

## 高程更正后的续接复核

- `sheet.publish.publish_overlap_sheet(source, surveys, sheets, survey_id, sheet_id)` 签发版本 2 包，返回 `packet_id` 和 `receipt`。读取调查固定的修订与幅范围，包内 JSON 含 `version`（整数 2）、`survey_id`、`revision_id`、`sheet_id`、`packet_id`、`coverage` 和 `evidence`。`sheet.store.read_sheet` 读原存文本，`sheets.read_receipt` 领回执。
- 证据表示：`evidence` 是覆盖内每个原格一条记录，含 `cell`（原格行列）、`corners`（西南、东南、西北、东北四角的高程，按同一垂直基准）和 `parts`（该格在调查等值高程下的 V1 分解，按 `part` 编号顺序，每片给出单位格坐标下的格边接触）。复核时用四角高程重算 double 线性等值集并逐格比对，因此可解释空集、整格、整边与孤立角点等退化形态，并能恢复 V1 的局部片、原 `part` 编号与精确格边接触。发行与复核之间只依赖存储的四角高程与调查几何，不需要源库；`revision_id`、`survey_id` 和 `coverage` 把包钉在原始调查与幅范围上，重开按原号复读。
- `review.assemble.issue_overlap_review(surveys, reports, old, new, *, before_commit=None)` 复核两侧，`old`、`new` 各为 `(survey_id, selected_sheet_ids, packets)`。每侧只用一个固定调查目录，可交不同调查号。按各自调查核对包身份、修订绑定与覆盖，两侧原点、轴距、等值高程及选中原格集合须精确相等，幅名与切幅方式可不同。两侧各按原 V1 接触规则完整归组。
- 组对只记在同一原格内确实共享正长度等值地段（连续曲线、轴对齐整段、整边或正面积公共区域）的两组之间；有限个公共点、空对应不记。同一对由多格见证也仅记一次，按 `(旧组序号, 新组序号)` 零起字典序去重。允许一对多、多对一。`report.old`、`report.new` 与 V1 `FrozenReport` 同口径，`report.pairs` 为元组序列。`ledger.history.read_overlap_review(reports, report_id)` 返回 `report_id`、`receipt`、`report`。领取只需报告库。
- 缺件、多件、重复幅、混单、V1 包、错修订、范围不符或无法解释的证据报 `ValueError`；未知调查号、修订号、领取号沿用 `LookupError`。幅件与回执、报告与回执各在同一事务内发布，失败不留新成果或回执。

## 错误与回归

非法测量、布局和选件报 `ValueError`，未知持久编号报 `LookupError`。幅件与其回执、报告与其回执分别一次提交。签发入口的可选关键字 `before_commit` 在两项写入后、同一事务提交前调用，异常向调用方传播并回滚这次写入。源更正、重新开单、再次复核和失败提交均保留旧成果。普通初始化不导入样例。

完整回归由 `python3.11 -B -m unittest discover -s tests -t . -v` 运行。测试经过登记、开单、签发和复核入口，核对手算鞍点、退化接触、独立 V1 包、反序与重切幅、隔幅选择、混单拒绝、提交中止及重开历史。`overlap_cases.py` 另以零等值、单位间距和零原点固定 V2 手算夹具，`python3.11 -B overlap_cases.py --v2` 经实际签发、移开高程源与幅件库后读取新报告库核对手算组对、拒绝与回滚。
