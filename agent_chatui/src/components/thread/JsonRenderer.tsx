interface JsonRendererProps {
  data: any;
  className?: string;
}

// 简单的SQL格式化函数
function formatSql(sql: string): string {
  // 移除字符串两端的引号（如果有）
  let cleanSql = sql.trim();
  if ((cleanSql.startsWith('"') && cleanSql.endsWith('"')) ||
      (cleanSql.startsWith("'") && cleanSql.endsWith("'"))) {
    cleanSql = cleanSql.slice(1, -1);
  }

  // 基本SQL格式化
  return cleanSql
    .replace(/\s+/g, ' ') // 合并多个空格
    .replace(/\bSELECT\b/gi, '\n  SELECT')
    .replace(/\bFROM\b/gi, '\nFROM')
    .replace(/\bWHERE\b/gi, '\nWHERE')
    .replace(/\bJOIN\b/gi, '\n  JOIN')
    .replace(/\bLEFT JOIN\b/gi, '\n  LEFT JOIN')
    .replace(/\bRIGHT JOIN\b/gi, '\n  RIGHT JOIN')
    .replace(/\bINNER JOIN\b/gi, '\n  INNER JOIN')
    .replace(/\bGROUP BY\b/gi, '\nGROUP BY')
    .replace(/\bORDER BY\b/gi, '\nORDER BY')
    .replace(/\bHAVING\b/gi, '\nHAVING')
    .replace(/\,/g, ',\n  ')
    .replace(/\bAND\b/gi, '\n  AND')
    .replace(/\bOR\b/gi, '\n  OR')
    .trim();
}

// 渲染单个SQL字段
function renderSqlField(sql: string, className = "") {
  return (
    <div className={`bg-blue-50 border border-blue-200 rounded-lg p-3 overflow-x-auto ${className}`}>
      <pre className="text-sm font-mono text-gray-800 whitespace-pre-wrap">
        {formatSql(sql)}
      </pre>
    </div>
  );
}

export function JsonRenderer({ data, className = "" }: JsonRendererProps) {
  // 如果是字符串，检查是否为参数名为"sql"的值
  if (typeof data === 'string') {
    return (
      <div className={`bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto ${className}`}>
        <pre className="text-sm font-mono text-gray-800 whitespace-pre-wrap">
          {data}
        </pre>
      </div>
    );
  }

  // 如果是对象，检查是否有"sql"字段
  if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
    const entries = Object.entries(data);

    // 如果只有一个sql字段，直接渲染格式化的SQL
    if (entries.length === 1 && entries[0][0] === 'sql' && typeof entries[0][1] === 'string') {
      return renderSqlField(entries[0][1], className);
    }

    // 如果有多个字段，检查是否包含sql字段
    const hasSqlField = entries.some(([key]) => key === 'sql');

    if (hasSqlField) {
      return (
        <div className={`space-y-3 ${className}`}>
          {entries.map(([key, value]) => {
            if (key === 'sql' && typeof value === 'string') {
              return (
                <div key={key}>
                  <div className="text-xs text-gray-600 font-medium mb-1 capitalize">{key}:</div>
                  {renderSqlField(value)}
                </div>
              );
            }

            return (
              <div key={key} className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                <div className="text-xs text-gray-600 font-medium mb-1 capitalize">{key}:</div>
                <div className="text-sm font-mono text-gray-800">
                  {typeof value === 'object' ? (
                    <JsonRenderer data={value} className="" />
                  ) : (
                    <pre className="whitespace-pre-wrap">{String(value)}</pre>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      );
    }
  }

  // 默认JSON渲染
  const jsonString = JSON.stringify(data, null, 2);
  return (
    <div className={`bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto ${className}`}>
      <pre className="text-sm font-mono text-gray-800 whitespace-pre-wrap">
        {jsonString}
      </pre>
    </div>
  );
}