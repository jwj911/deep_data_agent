"use client";

import React from "react";
import AutoChart from "@/components/ui/ant-charts";

// 定义业务数据的接口
interface SalesData {
  year: string;
  sales: number;
}

interface CategoryData {
  type: string;
  value: number;
}

const TestChartPage: React.FC = () => {
  // 模拟 Agent 返回的数据 - 场景 1：时间序列
  const timeSeriesData: SalesData[] = [
    { year: "2019", sales: 38 },
    { year: "2020", sales: 52 },
    { year: "2021", sales: 61 },
    { year: "2022", sales: 145 },
    { year: "2023", sales: 48 },
    { year: "2024", sales: 38 },
  ];

  // 模拟 Agent 返回的数据 - 场景 2：分类对比
  const categoryData: CategoryData[] = [
    { type: "电子产品", value: 27 },
    { type: "家居用品", value: 25 },
    { type: "服装", value: 18 },
    { type: "食品", value: 15 },
    { type: "书籍", value: 10 },
    { type: "其他", value: 5 },
  ];

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      <h1>Ant Charts 测试页面</h1>

      <section style={{ marginBottom: "40px" }}>
        <h3>分析结果 1：销售趋势 (Line/Area)</h3>
        <p style={{ color: "#666", fontSize: "14px" }}>
          Agent 识别意图：趋势分析 -- AVA 自动映射：X轴=year, Y轴=sales
        </p>
        <div
          style={{
            border: "1px solid #eee",
            padding: "10px",
            borderRadius: "8px",
          }}
        >
          <AutoChart
            data={timeSeriesData}
            height={300}
          />
        </div>
      </section>

      <section>
        <h3>分析结果 2：品类占比 (Pie/Interval)</h3>
        <p style={{ color: "#666", fontSize: "14px" }}>
          Agent 识别意图：占比分析 -- AVA 自动映射：Color=type, Angle/Y=value
        </p>
        <div
          style={{
            border: "1px solid #eee",
            padding: "10px",
            borderRadius: "8px",
          }}
        >
          <AutoChart
            data={categoryData}
            height={300}
          />
        </div>
      </section>
    </div>
  );
};

export default TestChartPage;
