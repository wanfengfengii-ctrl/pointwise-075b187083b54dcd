# 澄岸测绘等值地段续接

高程更正后，夜班需要把实际保留的等值地段续派给复测人员。`README.md` 说明已有登记、固定调查、单幅签发、断源单次复核和历史领取。三份样例即使有相同的旧式分幅接触，也可能需要分别签出有对应和空对应的报告。

## 分幅签发

新增 `sheet.publish.publish_overlap_sheet(source, surveys, sheets, survey_id, sheet_id, *, before_commit=None)`。参数与 `publish_sheet` 相同，返回带 `packet_id` 和 `receipt` 的签发结果。用 `sheet.store.read_sheet(sheets, packet_id)` 取原存 JSON 文本，用 `sheets.read_receipt(packet_id)` 领取回执。签发读取调查固定的修订与幅范围。

新版 JSON 包含 `version`、`survey_id`、`revision_id`、`sheet_id`、`packet_id`、`coverage` 和 `evidence`。`version` 为整数 2，其余身份字段为非空字符串，`coverage` 沿用 V1 原格半开范围。`evidence` 的内部表示由实现确定，并随交付说明。证据须能解释覆盖内每个原格的完整等值集，含空等值集、边界和退化形态，且可恢复 V1 口径下的局部片、原 `part` 编号及精确格边接触。

## 两侧复核及领取

新增 `review.assemble.issue_overlap_review(surveys, reports, old, new, *, before_commit=None)`。`old`、`new` 各为 `(survey_id, selected_sheet_ids, packets)` 三元组。每侧幅号及 JSON 文本均为可迭代对象，所选每幅恰好对应一个包，交件顺序任意。复核只使用离线调查目录、报告库及这两组包。按各自调查核对包身份和覆盖，两侧原点、轴距、等值高程及选中原格集合须精确相等。允许不同幅名和分幅方式。

单格使用原四角高程的双线性插值。坐标沿用 V1，局部西南角为 `(0,0)`，东北角为 `(1,1)`，插值等于调查等值高程的点属于该闭格的等值集。全零格指插值处处等于等值高程。两侧分别使用实际选件按 V1 接触规则完整归组，沿用组顺序和 `CellComponent`。原格相同的两侧局部片，若其交集包含一段非退化连续曲线或线段，则其所在组形成对应。格边上的整段与格内曲段同样有效。正面积的公共区域也包含这样的地段。只有有限个公共点时保留两侧原组，续接对为空。同一对可以由多格见证，报告内只保留一次。允许一对多、多对一以及无对应。可全量处理并复用原事务。

签发返回 `report_id` 和 `receipt`。新增 `ledger.history.read_overlap_review(reports, report_id)`，记录有 `report_id`、`receipt` 和 `report` 三个属性。`report.old`、`report.new` 分别有与 V1 `FrozenReport` 同口径的 `survey_id`、`adopted`、`groups`，其中 `adopted` 为按幅号排序的 `(sheet_id, packet_id)` 元组序列。`report.pairs` 是由 `(旧组序号, 新组序号)` 组成的元组，序号从零开始，按元组字典序排列且无重复。重开后按报告号读取已存结果，领取只需报告库。

已选幅缺件、多件、重复幅、混单、V1 包、错误修订绑定、范围不符或无法解释的证据抛 `ValueError`。未知调查号、修订号或领取号沿用 `LookupError`。幅件与幅件回执、报告与报告回执分别在同一事务内发布。两个新签发入口均沿用 `before_commit` 的时点，异常向调用方传播并回滚该次成果及回执。旧接口、旧件、旧报告和全部原回归保留。

## 手算夹具及运行

`overlap_cases.py` 以零等值、单位间距和零原点登记示例。高程矩阵从南到北，列从西到东。旧角值 `(-1,1,1,3)` 的线段端点为 `(0,1/2)` 和 `(1/2,0)`。更正 `(-2,2,2,6)` 保留整段，签出 `((0,0),)`。更正 `(-1,1,1,5)` 仅保留两个端点，签出 `()`。三者的单侧报告各保留一组。全零格对 `((1,-2),(-2,1))` 的两条曲支分别续接。双支格对整体取反后的同形格，签出 `((0,0),(1,1))`。两格共边样例在同一共边产生两个见证，整幅对拆幅报告只保留 `((0,0),)`。

`python3.11 -B overlap_cases.py` 核对现有 V1 证据对照。完成新入口后，`python3.11 -B overlap_cases.py --v2` 经实际签发、移开高程源和幅件库、读取新报告库实例核对手算组对。该命令还核对旧归组口径、异常拒绝和提交回滚，断言失败会退出非零。

交付时说明证据表示以及发行与复核之间如何保持原片身份，接通 `.pointwise-runtime.json` 中的验证和演示。现有清单以 `version` 1 和 `kind` 为 `cli` 标识，`setup` 是安装命令的 argv 数组列表，`verify`、`demo` 各为一条 argv 数组。验证运行原回归和续接核账并传播失败退出码。演示展示两种同端点更正的不同实际组对，以及源库、幅件库离线后重开按号领取的结果。
