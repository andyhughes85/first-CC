"""行业动量筛选 - 同花顺行业分类（支持自动降级）"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import TOP_INDUSTRIES_N


class IndustrySelector:
    """行业选择器 - 动量 + 拥挤度过滤"""

    def __init__(self):
        self.top_industries = []
        self.industry_data = pd.DataFrame()

    def update(self):
        """更新行业动量排名（同花顺数据源 + 自动降级）"""
        try:
            import akshare as ak

            # 获取行业列表（同花顺源，经测试可用）
            df = ak.stock_board_industry_name_ths()
            if df is None or df.empty:
                return self._fallback()
            industries = df["name"].tolist()
            print(f"[行业] 共 {len(industries)} 个行业")

            results = []
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")

            for ind in industries[:60]:  # 取前60个行业计算
                try:
                    # 尝试从同花顺获取行业K线
                    ind_df = ak.stock_board_industry_hist_em(
                        symbol=ind, period="daily",
                        start_date=start_date, end_date=end_date,
                    )
                    if ind_df is None or len(ind_df) < 30:
                        continue

                    close = ind_df["收盘价"].values
                    amount = ind_df["成交额"].values

                    mom_20d = close[-1] / close[-21] - 1
                    mom_5d = close[-1] / close[-6] - 1
                    amount_ma20 = pd.Series(amount).rolling(20).mean().iloc[-1]
                    amount_recent = amount[-5:].mean()
                    amount_ratio = amount_recent / amount_ma20 if amount_ma20 > 0 else 1

                    results.append({
                        "industry": ind,
                        "momentum_20d": round(mom_20d * 100, 2),
                        "momentum_5d": round(mom_5d * 100, 2),
                        "amount_ratio": round(amount_ratio, 2),
                    })
                except Exception:
                    continue

            if not results:
                return self._fallback()

            df_result = pd.DataFrame(results)
            # 过滤拥挤行业
            df_result = df_result[df_result["amount_ratio"] <= 1.5].copy()
            df_result = df_result.sort_values("momentum_20d", ascending=False)

            self.industry_data = df_result
            self.top_industries = df_result.head(TOP_INDUSTRIES_N)["industry"].tolist()

            print(f"[行业] 筛选出 {len(self.top_industries)} 个强势行业:")
            for _, row in df_result.head(10).iterrows():
                print(f"       {row['industry']:12s} 动量:{row['momentum_20d']:+.2f}%  "
                      f"成交比:{row['amount_ratio']:.2f}")
            return self.top_industries

        except Exception as e:
            print(f"[行业] 数据源异常: {e}")
            return self._fallback()

    def _fallback(self):
        """降级方案：常见强势行业硬编码 + 提示"""
        default_industries = [
            "半导体", "人工智能", "新能源", "汽车零部件", "医药生物",
        ]
        self.top_industries = default_industries[:TOP_INDUSTRIES_N]
        print(f"[行业] 使用默认行业列表: {self.top_industries}")
        print(f"       (提示: 网络不通, 请在本机运行以获取实时行业数据)")
        return self.top_industries

    def build_stock_industry_map(self, all_codes):
        """构建个股→行业映射（使用同花顺行业成分股）"""
        code_to_ind = {}
        try:
            import akshare as ak
            for ind in self.top_industries:
                try:
                    members = ak.stock_board_industry_cons_em(symbol=ind)
                    if members is not None and "代码" in members.columns:
                        for code in members["代码"].values:
                            if code in all_codes:
                                code_to_ind[code] = ind
                except Exception:
                    # 单行业失败不影响其他
                    continue
        except Exception:
            pass
        print(f"[行业] 映射完成: {len(code_to_ind)} 只个股")
        return code_to_ind

    def get_report(self):
        """获取行业报告文本"""
        if self.industry_data.empty:
            return "强势行业: " + ", ".join(self.top_industries)
        top10 = self.industry_data.head(10)
        lines = ["强势行业 Top 10:"]
        for _, row in top10.iterrows():
            flag = "★" if row["industry"] in self.top_industries else " "
            lines.append(f"  {flag} {row['industry']:12s}  "
                         f"动量:{row['momentum_20d']:+.2f}%  成交比:{row['amount_ratio']:.2f}")
        return "\n".join(lines)
