import React, { useEffect, useRef } from 'react';
// 引入 G2 的核心类 Chart 和配置类型 G2Spec
import { Chart, G2Spec } from '@antv/g2';
// 引入 AVA 的 Advisor 类
import { Advisor } from '@antv/ava';

// 定义组件 Props 接口
interface AutoChartProps {
  // 数据通常是一个对象数组，键是字符串，值可以是数字或字符串
  data: Record<string, any>[]; 
  height?: number;
  className?: string;
}

const AutoChart: React.FC<AutoChartProps> = ({ 
  data, 
  height = 400,
  className 
}) => {
  // 1. 指定 DOM 容器的类型为 HTMLDivElement
  const containerRef = useRef<HTMLDivElement>(null);
  
  // 2. 指定图表实例的类型为 Chart，初始值为 null
  const chartInstance = useRef<Chart | null>(null);

  useEffect(() => {
    // 数据为空或容器未挂载时直接返回
    if (!data || data.length === 0 || !containerRef.current) return;

    // --- 步骤 A: 调用 AVA 获取推荐 Spec ---
    const advisor = new Advisor();

    // AVA 的 advise 方法返回一个包含 spec 和分数的数组
    const results = advisor.advise({
      data: data,
    });

    if (results.length === 0) {
      console.warn('[AutoChart] AVA 无法分析当前数据，未生成推荐图表。');
      return;
    }

    // 取出分数最高的推荐结果
    const bestAdvice = results[0];
    
    // 这里是一个关键的 TS 处理：
    // AVA 输出的 spec 是通用的 JSON Schema，而 G2 接收的是 G2Spec。
    // 虽然结构一致，但 TS 可能会报错类型不完全匹配，所以使用 'as G2Spec' 进行断言。
    const spec = bestAdvice.spec as G2Spec;

    // --- 步骤 B: 初始化 AntV G2 并渲染 ---

    // 销毁旧实例，防止内存泄漏和重绘叠加
    if (chartInstance.current) {
      chartInstance.current.destroy();
    }

    // 初始化图表
    const chart = new Chart({
      container: containerRef.current,
      autoFit: true,
      height: height,
    });

    // 注入配置
    chart.options(spec);

    // 渲染
    chart.render();

    // 保存实例
    chartInstance.current = chart;

    // 清理函数
    return () => {
      if (chartInstance.current) {
        chartInstance.current.destroy();
        chartInstance.current = null;
      }
    };
  }, [data, height]); // 依赖项：数据或高度变化时重绘

  return (
    <div 
      ref={containerRef} 
      className={className}
      style={{ width: '100%', height: height }} 
    />
  );
};

export default AutoChart;