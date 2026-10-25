import { describe, expect, it } from 'vitest';
import { apiDocModules } from './apiDocsMockData';

describe('keyword V1.1 API docs catalog', () => {
  it('exposes every local endpoint with a fail-closed status', () => {
    const module = apiDocModules.find(item => item.key === 'keyword-planning-v11');
    expect(module).toBeDefined();
    const apis = module!.levels.flatMap(level => level.apis);
    expect(apis).toHaveLength(21);
    expect(new Set(apis.map(api => `${api.method} ${api.path}`)).size).toBe(21);
    expect(apis.every(api => api.authScope.includes('source_account_ref'))).toBe(true);
    expect(module!.desc).toContain('不可正式投放');
    expect(apis.find(api => api.path.endsWith('/internal-workbook'))?.successReturn)
      .toContain('不是官方上传模板');
  });
});
