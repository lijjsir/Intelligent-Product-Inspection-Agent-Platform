# Lab Detection Agent

Lab Detection Agent 是一个独立的 LangGraph 子图 Agent，用于真实实验室检测过程中的部分检测数据早期异常研判。

## 当前状态

- 独立子图开发中
- 不接入 Manager
- 不注册 capability
- 不接入 InspectionTask
- 不输出最终质量判定

## 核心输入

- **LabPartialDataContext**: 包含样品信息、检测计划、部分检测数据、历史基线等

## 核心输出

- **LabEarlyRiskAssessment**: 包含异常概率、风险等级、预警建议、补测优先级等

## 核心约束

- `can_make_final_verdict` 永远为 `false`
- 不替代完整实验室检测
- 数据不足时输出 `insufficient_data`
- 模型不可用时输出 `manual_review_required`
- 所有状态值必须在允许集合内

## 图结构

```
input_adapter → validate_lab_context → normalize_measurements → load_reference_context
    → compute_anomaly_features → llm_early_risk_reasoning → recommend_next_tests
    → finalize_assessment
```

## 后续接入路线

1. **阶段 B**: 作为 InspectionTaskGraph 内部协作 Agent
2. **阶段 C**: 通过 LabDetectionExecutor 接入 ManagerLoop
3. **阶段 D**: 与 StandardInterpretationAgent、QualityJudgementAgent、QualityReviewAgent 多 Agent 协作
