import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { apiFetch } from "../lib/api";

const MULTIFACTOR_PARAMS_DEFAULT = {
  strategy_key: "multifactor_v1",
  score_direction: "normal",
  buy_threshold: 75,
  sell_threshold: 50,
  max_positions: 5,
  slot_weight: 0.2,
  sector_max: 0.4,
  min_avg_amount_20d: 25000,
  market_exposure: { risk_on: 1.0, neutral: 0.7, risk_off: 0.4 },
  stop_loss_pct: 0.08,
  trail_stop_pct: 0.1,
  max_hold_days: 40,
  sell_confirm_days: 1,
  rotate_score_delta: 8,
  rotate_profit_ceiling: 0.05,
  min_hold_days_before_rotate: 3,
  score_ceiling: 100,
  slot_min_scale: 0.6,
  min_gross_exposure: 0,
  market_exposure_floor: 0.4,
  allow_buy_in_risk_off: true,
  allowed_boards: ["sh_main", "sz_main", "star", "gem"],
  enable_buy_tech_filter: true,
  entry_require_trend_alignment: false,
  entry_require_macd_positive: false,
  entry_min_sector_strength: 0,
  entry_sector_strength_quantile: 0,
  entry_rsi_min: 0,
  entry_rsi_max: 100,
  entry_max_pct_chg: 100,
  factor_weights: {
    stock_trend: 0.35,
    sector_strength: 0.25,
    value_quality: 0.25,
    liquidity_stability: 0.15,
  },
  signal_store_topk: 100,
  use_member_sector_mapping: true,
  sector_source_weights: { sw: 0.6, ci: 0.4 },
  max_daily_buy_count: 99,
  max_daily_sell_count: 99,
  max_daily_trade_count: 99,
  max_daily_rotate_count: 99,
  reentry_cooldown_days: 0,
  annual_trade_window_days: 252,
  max_annual_trade_count: 0,
  max_annual_buy_count: 0,
  max_annual_sell_count: 0,
};

const MUSECAT_PARAMS_DEFAULT = {
  ...MULTIFACTOR_PARAMS_DEFAULT,
  strategy_key: "musecat_v1",
  buy_threshold: 72,
  sell_threshold: 48,
  stop_loss_pct: 0.075,
  trail_stop_pct: 0.095,
  musecat_factor_weights: {
    momentum: 0.35,
    reversal: 0.2,
    quality: 0.25,
    liquidity: 0.2,
  },
  musecat_breakout_bonus: 5,
  musecat_drawdown_penalty: 6,
  musecat_macd_zero_axis_cross_bonus: 8,
  musecat_macd_zero_axis_depth_scale: 3,
  entry_require_macd_zero_axis_cross: false,
};

const STRATEGY_KEY_OPTIONS = [
  { value: "multifactor_v1", label: "Alpha (multifactor_v1)" },
  { value: "musecat_v1", label: "MuseCat (musecat_v1)" },
];

const resolveStrategyKey = (value) => {
  const text = String(value || "").trim();
  if (text === "musecat_v1") return "musecat_v1";
  return "multifactor_v1";
};

const getParamsDefaultByKey = (strategyKey) =>
  resolveStrategyKey(strategyKey) === "musecat_v1" ? MUSECAT_PARAMS_DEFAULT : MULTIFACTOR_PARAMS_DEFAULT;

const BOARD_OPTIONS = [
  { value: "sh_main", label: "沪市主板" },
  { value: "sz_main", label: "深市主板" },
  { value: "star", label: "科创板" },
  { value: "gem", label: "创业板" },
  { value: "bse", label: "北交所" },
  { value: "other", label: "其他板块" },
];

const formatDateTime = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const formatPct = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${(num * 100).toFixed(2)}%`;
};

const toInputValue = (value) => {
  if (value === null || value === undefined) return "";
  return String(value);
};

const toFloat = (value, fallback) => {
  if (value === null || value === undefined || value === "") return fallback;
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return num;
};

const toInt = (value, fallback) => {
  if (value === null || value === undefined || value === "") return fallback;
  const num = Number.parseInt(value, 10);
  if (!Number.isFinite(num)) return fallback;
  return num;
};

const normalizeScoreDirection = (value) => {
  const text = String(value || "").trim().toLowerCase();
  if (text === "reverse") return "reverse";
  return "normal";
};

const mergeParamsSnapshot = (snapshot, strategyKey) => {
  const defaults = getParamsDefaultByKey(strategyKey);
  const source = snapshot && typeof snapshot === "object" ? snapshot : {};
  const marketExposure = {
    ...defaults.market_exposure,
    ...(source.market_exposure && typeof source.market_exposure === "object"
      ? source.market_exposure
      : {}),
  };
  const sectorSourceWeights = {
    ...defaults.sector_source_weights,
    ...(source.sector_source_weights && typeof source.sector_source_weights === "object"
      ? source.sector_source_weights
      : {}),
  };
  const factorWeights = {
    ...MULTIFACTOR_PARAMS_DEFAULT.factor_weights,
    ...(source.factor_weights && typeof source.factor_weights === "object"
      ? source.factor_weights
      : {}),
  };
  const musecatFactorWeights = {
    ...(defaults.musecat_factor_weights && typeof defaults.musecat_factor_weights === "object"
      ? defaults.musecat_factor_weights
      : MUSECAT_PARAMS_DEFAULT.musecat_factor_weights),
    ...(source.musecat_factor_weights && typeof source.musecat_factor_weights === "object"
      ? source.musecat_factor_weights
      : {}),
  };

  let allowedBoards = defaults.allowed_boards;
  if (Array.isArray(source.allowed_boards)) {
    const normalized = source.allowed_boards
      .map((item) => String(item || "").trim().toLowerCase())
      .filter(Boolean);
    if (normalized.length > 0) allowedBoards = normalized;
  }

  return {
    ...defaults,
    ...source,
    strategy_key: resolveStrategyKey(strategyKey || source.strategy_key || defaults.strategy_key),
    score_direction: normalizeScoreDirection(source.score_direction || defaults.score_direction),
    market_exposure: marketExposure,
    sector_source_weights: sectorSourceWeights,
    factor_weights: factorWeights,
    musecat_factor_weights: musecatFactorWeights,
    allowed_boards: Array.from(new Set(allowedBoards)),
  };
};

const buildParamsForm = (snapshot, strategyKey) => {
  const merged = mergeParamsSnapshot(snapshot, strategyKey);
  const allowedSet = new Set(merged.allowed_boards);
  const musecatFactorWeights =
    merged.musecat_factor_weights && typeof merged.musecat_factor_weights === "object"
      ? merged.musecat_factor_weights
      : MUSECAT_PARAMS_DEFAULT.musecat_factor_weights;
  return {
    strategy_key: resolveStrategyKey(merged.strategy_key || strategyKey),
    score_direction: normalizeScoreDirection(merged.score_direction),
    buy_threshold: toInputValue(merged.buy_threshold),
    sell_threshold: toInputValue(merged.sell_threshold),
    max_positions: toInputValue(merged.max_positions),
    slot_weight: toInputValue(merged.slot_weight),
    sector_max: toInputValue(merged.sector_max),
    min_avg_amount_20d: toInputValue(merged.min_avg_amount_20d),
    market_exposure_risk_on: toInputValue(merged.market_exposure.risk_on),
    market_exposure_neutral: toInputValue(merged.market_exposure.neutral),
    market_exposure_risk_off: toInputValue(merged.market_exposure.risk_off),
    stop_loss_pct: toInputValue(merged.stop_loss_pct),
    trail_stop_pct: toInputValue(merged.trail_stop_pct),
    max_hold_days: toInputValue(merged.max_hold_days),
    sell_confirm_days: toInputValue(merged.sell_confirm_days),
    rotate_score_delta: toInputValue(merged.rotate_score_delta),
    rotate_profit_ceiling: toInputValue(merged.rotate_profit_ceiling),
    min_hold_days_before_rotate: toInputValue(merged.min_hold_days_before_rotate),
    score_ceiling: toInputValue(merged.score_ceiling),
    slot_min_scale: toInputValue(merged.slot_min_scale),
    min_gross_exposure: toInputValue(merged.min_gross_exposure),
    market_exposure_floor: toInputValue(merged.market_exposure_floor),
    allow_buy_in_risk_off: Boolean(merged.allow_buy_in_risk_off),
    entry_require_trend_alignment: Boolean(merged.entry_require_trend_alignment),
    entry_require_macd_positive: Boolean(merged.entry_require_macd_positive),
    entry_require_macd_zero_axis_cross: Boolean(merged.entry_require_macd_zero_axis_cross),
    entry_min_sector_strength: toInputValue(merged.entry_min_sector_strength),
    entry_sector_strength_quantile: toInputValue(merged.entry_sector_strength_quantile),
    entry_rsi_min: toInputValue(merged.entry_rsi_min),
    entry_rsi_max: toInputValue(merged.entry_rsi_max),
    entry_max_pct_chg: toInputValue(merged.entry_max_pct_chg),
    factor_weights_stock_trend: toInputValue((merged.factor_weights || {}).stock_trend),
    factor_weights_sector_strength: toInputValue((merged.factor_weights || {}).sector_strength),
    factor_weights_value_quality: toInputValue((merged.factor_weights || {}).value_quality),
    factor_weights_liquidity_stability: toInputValue((merged.factor_weights || {}).liquidity_stability),
    musecat_factor_weights_momentum: toInputValue(musecatFactorWeights.momentum),
    musecat_factor_weights_reversal: toInputValue(musecatFactorWeights.reversal),
    musecat_factor_weights_quality: toInputValue(musecatFactorWeights.quality),
    musecat_factor_weights_liquidity: toInputValue(musecatFactorWeights.liquidity),
    musecat_breakout_bonus: toInputValue(merged.musecat_breakout_bonus),
    musecat_drawdown_penalty: toInputValue(merged.musecat_drawdown_penalty),
    musecat_macd_zero_axis_cross_bonus: toInputValue(merged.musecat_macd_zero_axis_cross_bonus),
    musecat_macd_zero_axis_depth_scale: toInputValue(merged.musecat_macd_zero_axis_depth_scale),
    enable_buy_tech_filter: Boolean(merged.enable_buy_tech_filter),
    signal_store_topk: toInputValue(merged.signal_store_topk),
    use_member_sector_mapping: Boolean(merged.use_member_sector_mapping),
    sector_source_weights_sw: toInputValue(merged.sector_source_weights.sw),
    sector_source_weights_ci: toInputValue(merged.sector_source_weights.ci),
    max_daily_buy_count: toInputValue(merged.max_daily_buy_count),
    max_daily_sell_count: toInputValue(merged.max_daily_sell_count),
    max_daily_trade_count: toInputValue(merged.max_daily_trade_count),
    max_daily_rotate_count: toInputValue(merged.max_daily_rotate_count),
    reentry_cooldown_days: toInputValue(merged.reentry_cooldown_days),
    annual_trade_window_days: toInputValue(merged.annual_trade_window_days),
    max_annual_trade_count: toInputValue(merged.max_annual_trade_count),
    max_annual_buy_count: toInputValue(merged.max_annual_buy_count),
    max_annual_sell_count: toInputValue(merged.max_annual_sell_count),
    allowed_boards_sh_main: allowedSet.has("sh_main"),
    allowed_boards_sz_main: allowedSet.has("sz_main"),
    allowed_boards_star: allowedSet.has("star"),
    allowed_boards_gem: allowedSet.has("gem"),
    allowed_boards_bse: allowedSet.has("bse"),
    allowed_boards_other: allowedSet.has("other"),
  };
};

const buildParamsSnapshot = (form, strategyKey) => {
  const key = resolveStrategyKey(strategyKey || form.strategy_key);
  const defaults = getParamsDefaultByKey(key);
  const allowedBoards = BOARD_OPTIONS.filter((item) => Boolean(form[`allowed_boards_${item.value}`])).map(
    (item) => item.value
  );
  const payload = {
    strategy_key: key,
    score_direction: normalizeScoreDirection(form.score_direction),
    buy_threshold: toFloat(form.buy_threshold, defaults.buy_threshold),
    sell_threshold: toFloat(form.sell_threshold, defaults.sell_threshold),
    max_positions: toInt(form.max_positions, defaults.max_positions),
    slot_weight: toFloat(form.slot_weight, defaults.slot_weight),
    sector_max: toFloat(form.sector_max, defaults.sector_max),
    min_avg_amount_20d: toFloat(form.min_avg_amount_20d, defaults.min_avg_amount_20d),
    market_exposure: {
      risk_on: toFloat(form.market_exposure_risk_on, defaults.market_exposure.risk_on),
      neutral: toFloat(form.market_exposure_neutral, defaults.market_exposure.neutral),
      risk_off: toFloat(form.market_exposure_risk_off, defaults.market_exposure.risk_off),
    },
    stop_loss_pct: toFloat(form.stop_loss_pct, defaults.stop_loss_pct),
    trail_stop_pct: toFloat(form.trail_stop_pct, defaults.trail_stop_pct),
    max_hold_days: toInt(form.max_hold_days, defaults.max_hold_days),
    sell_confirm_days: toInt(form.sell_confirm_days, defaults.sell_confirm_days),
    rotate_score_delta: toFloat(form.rotate_score_delta, defaults.rotate_score_delta),
    rotate_profit_ceiling: toFloat(form.rotate_profit_ceiling, defaults.rotate_profit_ceiling),
    min_hold_days_before_rotate: toInt(form.min_hold_days_before_rotate, defaults.min_hold_days_before_rotate),
    score_ceiling: toFloat(form.score_ceiling, defaults.score_ceiling),
    slot_min_scale: toFloat(form.slot_min_scale, defaults.slot_min_scale),
    min_gross_exposure: toFloat(form.min_gross_exposure, defaults.min_gross_exposure),
    market_exposure_floor: toFloat(form.market_exposure_floor, defaults.market_exposure_floor),
    allow_buy_in_risk_off: Boolean(form.allow_buy_in_risk_off),
    allowed_boards: allowedBoards.length > 0 ? allowedBoards : defaults.allowed_boards,
    enable_buy_tech_filter: Boolean(form.enable_buy_tech_filter),
    entry_require_trend_alignment: Boolean(form.entry_require_trend_alignment),
    entry_require_macd_positive: Boolean(form.entry_require_macd_positive),
    entry_require_macd_zero_axis_cross: Boolean(form.entry_require_macd_zero_axis_cross),
    entry_min_sector_strength: toFloat(form.entry_min_sector_strength, defaults.entry_min_sector_strength),
    entry_sector_strength_quantile: toFloat(
      form.entry_sector_strength_quantile,
      defaults.entry_sector_strength_quantile
    ),
    entry_rsi_min: toFloat(form.entry_rsi_min, defaults.entry_rsi_min),
    entry_rsi_max: toFloat(form.entry_rsi_max, defaults.entry_rsi_max),
    entry_max_pct_chg: toFloat(form.entry_max_pct_chg, defaults.entry_max_pct_chg),
    signal_store_topk: toInt(form.signal_store_topk, defaults.signal_store_topk),
    use_member_sector_mapping: Boolean(form.use_member_sector_mapping),
    sector_source_weights: {
      sw: toFloat(form.sector_source_weights_sw, defaults.sector_source_weights.sw),
      ci: toFloat(form.sector_source_weights_ci, defaults.sector_source_weights.ci),
    },
    max_daily_buy_count: toInt(form.max_daily_buy_count, defaults.max_daily_buy_count),
    max_daily_sell_count: toInt(form.max_daily_sell_count, defaults.max_daily_sell_count),
    max_daily_trade_count: toInt(form.max_daily_trade_count, defaults.max_daily_trade_count),
    max_daily_rotate_count: toInt(form.max_daily_rotate_count, defaults.max_daily_rotate_count),
    reentry_cooldown_days: toInt(form.reentry_cooldown_days, defaults.reentry_cooldown_days),
    annual_trade_window_days: toInt(form.annual_trade_window_days, defaults.annual_trade_window_days),
    max_annual_trade_count: toInt(form.max_annual_trade_count, defaults.max_annual_trade_count),
    max_annual_buy_count: toInt(form.max_annual_buy_count, defaults.max_annual_buy_count),
    max_annual_sell_count: toInt(form.max_annual_sell_count, defaults.max_annual_sell_count),
  };
  if (key === "musecat_v1") {
    payload.musecat_factor_weights = {
      momentum: toFloat(form.musecat_factor_weights_momentum, defaults.musecat_factor_weights.momentum),
      reversal: toFloat(form.musecat_factor_weights_reversal, defaults.musecat_factor_weights.reversal),
      quality: toFloat(form.musecat_factor_weights_quality, defaults.musecat_factor_weights.quality),
      liquidity: toFloat(form.musecat_factor_weights_liquidity, defaults.musecat_factor_weights.liquidity),
    };
    payload.musecat_breakout_bonus = toFloat(form.musecat_breakout_bonus, defaults.musecat_breakout_bonus);
    payload.musecat_drawdown_penalty = toFloat(form.musecat_drawdown_penalty, defaults.musecat_drawdown_penalty);
    payload.musecat_macd_zero_axis_cross_bonus = toFloat(
      form.musecat_macd_zero_axis_cross_bonus,
      defaults.musecat_macd_zero_axis_cross_bonus
    );
    payload.musecat_macd_zero_axis_depth_scale = toFloat(
      form.musecat_macd_zero_axis_depth_scale,
      defaults.musecat_macd_zero_axis_depth_scale
    );
  } else {
    payload.factor_weights = {
      stock_trend: toFloat(form.factor_weights_stock_trend, defaults.factor_weights.stock_trend),
      sector_strength: toFloat(form.factor_weights_sector_strength, defaults.factor_weights.sector_strength),
      value_quality: toFloat(form.factor_weights_value_quality, defaults.factor_weights.value_quality),
      liquidity_stability: toFloat(form.factor_weights_liquidity_stability, defaults.factor_weights.liquidity_stability),
    };
  }
  return payload;
};

const formatParamsSnapshotJson = (snapshot) => JSON.stringify(snapshot || {}, null, 2);

const parseParamsSnapshotJson = (text) => {
  const parsed = JSON.parse(String(text || "").trim() || "{}");
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("params_snapshot 必须是 JSON 对象");
  }
  return parsed;
};

export default function StrategiesPage() {
  const router = useRouter();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [versions, setVersions] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedRunIds, setSelectedRunIds] = useState([]);

  const [newName, setNewName] = useState("");
  const [newStrategyKey, setNewStrategyKey] = useState("multifactor_v1");
  const [newDescription, setNewDescription] = useState("");
  const [newOwner, setNewOwner] = useState("");

  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [versionCodeRef, setVersionCodeRef] = useState("main");
  const [versionChangeLog, setVersionChangeLog] = useState("");
  const [paramsForm, setParamsForm] = useState(() => buildParamsForm(MULTIFACTOR_PARAMS_DEFAULT, "multifactor_v1"));
  const [paramsJsonText, setParamsJsonText] = useState(() =>
    formatParamsSnapshotJson(buildParamsSnapshot(buildParamsForm(MULTIFACTOR_PARAMS_DEFAULT, "multifactor_v1"), "multifactor_v1"))
  );
  const [paramsJsonError, setParamsJsonError] = useState("");
  const [paramsSeedKey, setParamsSeedKey] = useState("");
  const [paramsFormDirty, setParamsFormDirty] = useState(false);

  const [runStartDate, setRunStartDate] = useState("20250101");
  const [runEndDate, setRunEndDate] = useState("20260206");
  const [runType, setRunType] = useState("range");
  const [runCreating, setRunCreating] = useState(false);
  const [paramsModalRun, setParamsModalRun] = useState(null);
  const [strategyModalOpen, setStrategyModalOpen] = useState(false);
  const [versionModalOpen, setVersionModalOpen] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState("");
  const [strategiesCollapsed, setStrategiesCollapsed] = useState(false);
  const [versionsCollapsed, setVersionsCollapsed] = useState(false);

  const totalPages = useMemo(() => Math.max(Math.ceil(total / pageSize), 1), [total, pageSize]);
  const selectedStrategy = useMemo(
    () => items.find((item) => item.strategy_id === selectedStrategyId) || null,
    [items, selectedStrategyId]
  );
  const currentStrategyKey = resolveStrategyKey(selectedStrategy?.strategy_key);

  const setParamValue = (key, value) => {
    setParamsForm((prev) => {
      const next = { ...prev, [key]: value };
      setParamsJsonText(formatParamsSnapshotJson(buildParamsSnapshot(next, currentStrategyKey)));
      return next;
    });
    setParamsJsonError("");
    setParamsFormDirty(true);
  };

  const handleParamsJsonChange = (value) => {
    setParamsJsonText(value);
    setParamsFormDirty(true);
    try {
      const parsed = parseParamsSnapshotJson(value);
      setParamsForm(buildParamsForm(parsed, currentStrategyKey));
      setParamsJsonError("");
    } catch (err) {
      setParamsJsonError(err.message || "JSON 格式错误");
    }
  };

  const loadStrategies = async (targetPage = page) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(targetPage));
      params.set("page_size", String(pageSize));
      const res = await apiFetch(`/strategies?${params.toString()}`);
      if (!res.ok) throw new Error(`加载策略失败: ${res.status}`);
      const data = await res.json();
      const list = data.items || [];
      setItems(list);
      setTotal(data.total || 0);
      if (!selectedStrategyId && list.length > 0) {
        setSelectedStrategyId(list[0].strategy_id);
      }
    } catch (err) {
      setError(err.message || "加载策略失败");
    } finally {
      setLoading(false);
    }
  };

  const loadStrategyDetails = async (strategyId) => {
    if (!strategyId) return;
    try {
      const [versionRes, runRes] = await Promise.all([
        apiFetch(`/strategies/${strategyId}/versions`),
        apiFetch(`/backtests?strategy_id=${encodeURIComponent(strategyId)}&page=1&page_size=100`),
      ]);
      if (!versionRes.ok) throw new Error(`加载版本失败: ${versionRes.status}`);
      if (!runRes.ok) throw new Error(`加载回测失败: ${runRes.status}`);
      const versionData = await versionRes.json();
      const runData = await runRes.json();
      const versionItems = versionData.items || [];
      setVersions(versionItems);
      setRuns(runData.items || []);
      setSelectedRunIds([]);
      if (versionItems.length > 0) {
        setSelectedVersionId((prev) =>
          versionItems.find((item) => item.strategy_version_id === prev) ? prev : versionItems[0].strategy_version_id
        );
      } else {
        setSelectedVersionId("");
      }
    } catch (err) {
      setError(err.message || "加载详情失败");
    }
  };

  useEffect(() => {
    loadStrategies();
  }, [page]);

  useEffect(() => {
    if (!selectedStrategyId) return;
    loadStrategyDetails(selectedStrategyId);
  }, [selectedStrategyId]);

  useEffect(() => {
    if (!selectedStrategyId) return;
    const latest = versions[0];
    const nextSeedKey = `${selectedStrategyId}:${latest?.strategy_version_id || "default"}:${currentStrategyKey}`;
    if (nextSeedKey !== paramsSeedKey || !paramsFormDirty) {
      if (nextSeedKey !== paramsSeedKey) {
        const nextForm = buildParamsForm(latest?.params_snapshot || getParamsDefaultByKey(currentStrategyKey), currentStrategyKey);
        setParamsForm(nextForm);
        setParamsJsonText(formatParamsSnapshotJson(buildParamsSnapshot(nextForm, currentStrategyKey)));
        setParamsJsonError("");
        setParamsFormDirty(false);
        setParamsSeedKey(nextSeedKey);
      }
    }
  }, [selectedStrategyId, versions, paramsSeedKey, paramsFormDirty, currentStrategyKey]);

  const createStrategy = async (event) => {
    event.preventDefault();
    setError("");
    try {
      const res = await apiFetch("/strategies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          strategy_key: newStrategyKey,
          description: newDescription.trim(),
          owner: newOwner.trim(),
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `创建失败: ${res.status}`);
      }
      const item = await res.json();
      setNewName("");
      setNewStrategyKey("multifactor_v1");
      setNewDescription("");
      setNewOwner("");
      setStrategyModalOpen(false);
      await loadStrategies(1);
      setPage(1);
      setSelectedStrategyId(item.strategy_id);
    } catch (err) {
      setError(err.message || "创建失败");
    }
  };

  const createVersion = async (event) => {
    event.preventDefault();
    if (!selectedStrategyId) return;
    setError("");
    let paramsSnapshot = {};
    try {
      paramsSnapshot = parseParamsSnapshotJson(paramsJsonText);
      paramsSnapshot.strategy_key = currentStrategyKey;
      setParamsJsonError("");
    } catch (err) {
      const message = err.message || "params_snapshot JSON 解析失败";
      setParamsJsonError(message);
      setError(message);
      return;
    }
    try {
      const res = await apiFetch(`/strategies/${selectedStrategyId}/versions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          params_snapshot: paramsSnapshot,
          code_ref: versionCodeRef.trim(),
          change_log: versionChangeLog.trim(),
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `发布版本失败: ${res.status}`);
      }
      const item = await res.json();
      setVersionChangeLog("");
      setSelectedVersionId(item.strategy_version_id);
      await loadStrategyDetails(selectedStrategyId);
      setVersionModalOpen(false);
      window.alert("版本发布成功");
    } catch (err) {
      setError(err.message || "发布版本失败");
    }
  };

  const createRunMeta = async (event) => {
    event.preventDefault();
    if (!selectedStrategyId || !selectedVersionId) return;
    setError("");
    setRunCreating(true);
    try {
      const res = await apiFetch("/backtests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: selectedStrategyId,
          strategy_version_id: selectedVersionId,
          start_date: runStartDate.replaceAll("-", ""),
          end_date: runEndDate.replaceAll("-", ""),
          run_type: runType,
          initial_capital: 1000000,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `创建回测失败: ${res.status}`);
      }
      const item = await res.json();
      await loadStrategyDetails(selectedStrategyId);
      router.push(`/backtests/${item.run_id}`);
    } catch (err) {
      setError(err.message || "创建回测失败");
    } finally {
      setRunCreating(false);
    }
  };

  const toggleRunSelect = (runId, checked) => {
    setSelectedRunIds((prev) => {
      if (checked) {
        if (prev.includes(runId)) return prev;
        if (prev.length >= 5) return prev;
        return [...prev, runId];
      }
      return prev.filter((item) => item !== runId);
    });
  };

  const goCompare = () => {
    if (selectedRunIds.length < 2) return;
    const query = encodeURIComponent(selectedRunIds.join(","));
    router.push(`/backtests/compare?run_ids=${query}`);
  };

  const showRunParams = (run) => {
    setParamsModalRun(run || null);
  };

  const closeRunParams = () => {
    setParamsModalRun(null);
  };

  const closeVersionModal = () => {
    setVersionModalOpen(false);
  };

  const openVersionModal = () => {
    setParamsJsonText(formatParamsSnapshotJson(buildParamsSnapshot(paramsForm, currentStrategyKey)));
    setParamsJsonError("");
    setVersionModalOpen(true);
  };

  const closeStrategyModal = () => {
    setStrategyModalOpen(false);
  };

  const deleteRun = async (runId) => {
    if (!runId) return;
    const confirmed = window.confirm(`确认删除回测 Run ${runId} 吗？该操作会同时删除净值、交易、持仓、信号明细。`);
    if (!confirmed) return;
    setDeletingRunId(runId);
    setError("");
    try {
      const res = await apiFetch(`/backtests/${encodeURIComponent(runId)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `删除失败: ${res.status}`);
      }
      await Promise.all([loadStrategyDetails(selectedStrategyId), loadStrategies(page)]);
    } catch (err) {
      setError(err.message || "删除失败");
    } finally {
      setDeletingRunId("");
    }
  };

  const workspaceClass = [
    "strategy-workspace",
    strategiesCollapsed ? "is-strategies-collapsed" : "",
    versionsCollapsed ? "is-versions-collapsed" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <main className="page">
      <header className="header">
        <div>
          <p className="eyebrow">Strategy Center</p>
          <h1>策略中心</h1>
          <p className="subtitle">左侧策略，中间版本，右侧回测</p>
        </div>
        <div className="header-actions">
          <button className="primary" onClick={() => loadStrategies(page)} disabled={loading}>
            {loading ? "刷新中..." : "刷新"}
          </button>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <div className={workspaceClass}>
        {strategiesCollapsed ? (
          <section className="strategy-column strategy-column--strategies strategy-column--collapsed-rail">
            <button
              type="button"
              className="column-rail-btn"
              onClick={() => setStrategiesCollapsed(false)}
              title="展开策略列"
            >
              <span className="column-rail-icon">›</span>
              <span className="column-rail-label">策略</span>
            </button>
          </section>
        ) : (
          <section className="strategy-column strategy-column--strategies">
          <section className="panel">
            <div className="panel-title-row">
              <h3 style={{ margin: 0 }}>策略列表</h3>
              <div className="panel-title-actions">
                <span className="subtitle" style={{ margin: 0 }}>
                  点击行可切换策略
                </span>
                <button type="button" className="primary" onClick={() => setStrategyModalOpen(true)}>
                  创建策略
                </button>
                <button type="button" className="link-button" onClick={() => setStrategiesCollapsed(true)}>
                  收起策略
                </button>
              </div>
            </div>
            <div className="table-wrap compact-table strategies-table" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>策略ID</th>
                    <th>名称</th>
                    <th>策略键</th>
                    <th>状态</th>
                    <th>最近Run</th>
                    <th>累计收益</th>
                    <th>更新时间</th>
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="empty">
                        暂无策略
                      </td>
                    </tr>
                  ) : (
                    items.map((item) => (
                      <tr
                        key={item.strategy_id}
                        className={selectedStrategyId === item.strategy_id ? "is-selected" : ""}
                        onClick={() => setSelectedStrategyId(item.strategy_id)}
                        style={{ cursor: "pointer" }}
                      >
                        <td>{item.strategy_id}</td>
                        <td>{item.name}</td>
                        <td>{item.strategy_key || "multifactor_v1"}</td>
                        <td>{item.status || "-"}</td>
                        <td>{item.latest_run_id || "-"}</td>
                        <td>{formatPct(item?.latest_summary?.total_return)}</td>
                        <td>{formatDateTime(item.updated_at)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <div className="pagination">
            <span>
              共 {total} 条，第 {page} / {totalPages} 页
            </span>
            <div className="pager-actions">
              <button type="button" disabled={page <= 1} onClick={() => setPage((v) => Math.max(v - 1, 1))}>
                上一页
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((v) => Math.min(v + 1, totalPages))}
              >
                下一页
              </button>
            </div>
          </div>
        </section>
        )}

        {versionsCollapsed ? (
          <section className="strategy-column strategy-column--versions strategy-column--collapsed-rail">
            <button
              type="button"
              className="column-rail-btn"
              onClick={() => setVersionsCollapsed(false)}
              title="展开版本列"
            >
              <span className="column-rail-icon">›</span>
              <span className="column-rail-label">版本</span>
            </button>
          </section>
        ) : (
          <section className="strategy-column strategy-column--versions">
          <section className="panel">
            <div className="panel-title-row">
              <h3 style={{ margin: 0 }}>版本列表</h3>
              <div className="panel-title-actions">
                <span className="subtitle" style={{ margin: 0 }}>
                  当前策略: {selectedStrategyId || "-"} / {currentStrategyKey}
                </span>
                <button
                  type="button"
                  className="primary"
                  onClick={openVersionModal}
                  disabled={!selectedStrategyId}
                >
                  创建版本
                </button>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setVersionModalOpen(false);
                    setVersionsCollapsed(true);
                  }}
                >
                  收起版本
                </button>
              </div>
            </div>
            {selectedStrategyId ? (
              <div className="table-wrap compact-table versions-table" style={{ marginTop: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th>版本</th>
                      <th>版本ID</th>
                      <th>策略键</th>
                      <th>Code Ref</th>
                      <th>创建时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="empty">
                          暂无版本
                        </td>
                      </tr>
                    ) : (
                      versions.map((item) => (
                        <tr
                          key={item.strategy_version_id}
                          className={selectedVersionId === item.strategy_version_id ? "is-selected" : ""}
                          onClick={() => setSelectedVersionId(item.strategy_version_id)}
                          style={{ cursor: "pointer" }}
                        >
                          <td>{item.version || "-"}</td>
                          <td>{item.strategy_version_id}</td>
                          <td>{item.strategy_key || selectedStrategy?.strategy_key || "-"}</td>
                          <td>{item.code_ref || "-"}</td>
                          <td>{formatDateTime(item.created_at)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty" style={{ marginTop: 12 }}>
                请先在左侧选择策略
              </div>
            )}
          </section>

          {versionModalOpen ? (
            <div
              className="modal-backdrop"
              onClick={(event) => {
                if (event.target === event.currentTarget) closeVersionModal();
              }}
            >
              <div className="modal-card modal-card--version-create">
                <div className="modal-header">
                  <h3 style={{ margin: 0 }}>创建版本（策略: {selectedStrategyId || "-"}）</h3>
                  <button type="button" className="link-button" onClick={closeVersionModal}>
                    关闭
                  </button>
                </div>
                {selectedStrategyId ? (
                  <form onSubmit={createVersion} className="version-form-layout">
                <div className="version-modal-layout">
                <div className="version-form-main">
                <div className="form-grid version-meta-grid" style={{ marginBottom: 10 }}>
                  <label className="field">
                    <span>Code Ref</span>
                    <input value={versionCodeRef} onChange={(e) => setVersionCodeRef(e.target.value)} />
                  </label>
                  <label className="field">
                    <span>变更说明</span>
                    <input value={versionChangeLog} onChange={(e) => setVersionChangeLog(e.target.value)} />
                  </label>
                </div>

                <div className="version-params-grid">
                  <label className="field">
                    <span>strategy_key</span>
                    <small className="field-hint">由策略定义绑定，版本中不可修改</small>
                    <input value={currentStrategyKey} readOnly />
                  </label>
                  <label className="field">
                    <span>score_direction</span>
                    <small className="field-hint">打分方向，reverse=分数越低越好</small>
                    <select
                      value={paramsForm.score_direction}
                      onChange={(e) => setParamValue("score_direction", e.target.value)}
                    >
                      <option value="reverse">reverse</option>
                      <option value="normal">normal</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>buy_threshold</span>
                    <small className="field-hint">买入阈值，分数达到该值才考虑买入</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.buy_threshold}
                      onChange={(e) => setParamValue("buy_threshold", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>sell_threshold</span>
                    <small className="field-hint">卖出阈值，分数低于该值触发卖出</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.sell_threshold}
                      onChange={(e) => setParamValue("sell_threshold", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_positions</span>
                    <small className="field-hint">最大持仓股票数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_positions}
                      onChange={(e) => setParamValue("max_positions", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>slot_weight</span>
                    <small className="field-hint">单仓基础权重</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.slot_weight}
                      onChange={(e) => setParamValue("slot_weight", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>sector_max</span>
                    <small className="field-hint">单行业最大仓位上限</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.sector_max}
                      onChange={(e) => setParamValue("sector_max", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>min_avg_amount_20d</span>
                    <small className="field-hint">20日平均成交额下限（万元）</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.min_avg_amount_20d}
                      onChange={(e) => setParamValue("min_avg_amount_20d", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>market_exposure.risk_on</span>
                    <small className="field-hint">强势市场仓位系数</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.market_exposure_risk_on}
                      onChange={(e) => setParamValue("market_exposure_risk_on", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>market_exposure.neutral</span>
                    <small className="field-hint">震荡市场仓位系数</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.market_exposure_neutral}
                      onChange={(e) => setParamValue("market_exposure_neutral", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>market_exposure.risk_off</span>
                    <small className="field-hint">弱势市场仓位系数</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.market_exposure_risk_off}
                      onChange={(e) => setParamValue("market_exposure_risk_off", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>stop_loss_pct</span>
                    <small className="field-hint">固定止损比例</small>
                    <input
                      type="number"
                      step="0.001"
                      value={paramsForm.stop_loss_pct}
                      onChange={(e) => setParamValue("stop_loss_pct", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>trail_stop_pct</span>
                    <small className="field-hint">移动止损比例</small>
                    <input
                      type="number"
                      step="0.001"
                      value={paramsForm.trail_stop_pct}
                      onChange={(e) => setParamValue("trail_stop_pct", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_hold_days</span>
                    <small className="field-hint">最大持有天数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_hold_days}
                      onChange={(e) => setParamValue("max_hold_days", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>sell_confirm_days</span>
                    <small className="field-hint">卖出确认天数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.sell_confirm_days}
                      onChange={(e) => setParamValue("sell_confirm_days", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>rotate_score_delta</span>
                    <small className="field-hint">换仓最低分差</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.rotate_score_delta}
                      onChange={(e) => setParamValue("rotate_score_delta", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>rotate_profit_ceiling</span>
                    <small className="field-hint">换仓时原仓最大收益限制</small>
                    <input
                      type="number"
                      step="0.001"
                      value={paramsForm.rotate_profit_ceiling}
                      onChange={(e) => setParamValue("rotate_profit_ceiling", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>min_hold_days_before_rotate</span>
                    <small className="field-hint">持有至少多少天才允许换仓</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.min_hold_days_before_rotate}
                      onChange={(e) => setParamValue("min_hold_days_before_rotate", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>score_ceiling</span>
                    <small className="field-hint">打分上限，用于仓位缩放</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.score_ceiling}
                      onChange={(e) => setParamValue("score_ceiling", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>slot_min_scale</span>
                    <small className="field-hint">单仓最小缩放比例</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.slot_min_scale}
                      onChange={(e) => setParamValue("slot_min_scale", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>min_gross_exposure</span>
                    <small className="field-hint">组合最低总仓位</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.min_gross_exposure}
                      onChange={(e) => setParamValue("min_gross_exposure", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>market_exposure_floor</span>
                    <small className="field-hint">市场仓位下限</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.market_exposure_floor}
                      onChange={(e) => setParamValue("market_exposure_floor", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>entry_min_sector_strength</span>
                    <small className="field-hint">入场最小行业强度</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.entry_min_sector_strength}
                      onChange={(e) => setParamValue("entry_min_sector_strength", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>entry_sector_strength_quantile</span>
                    <small className="field-hint">板块强度分位过滤(0~1)</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.entry_sector_strength_quantile}
                      onChange={(e) => setParamValue("entry_sector_strength_quantile", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>entry_rsi_min</span>
                    <small className="field-hint">入场 RSI 下限</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.entry_rsi_min}
                      onChange={(e) => setParamValue("entry_rsi_min", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>entry_rsi_max</span>
                    <small className="field-hint">入场 RSI 上限</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.entry_rsi_max}
                      onChange={(e) => setParamValue("entry_rsi_max", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>entry_max_pct_chg</span>
                    <small className="field-hint">入场当日涨幅上限(%)</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.entry_max_pct_chg}
                      onChange={(e) => setParamValue("entry_max_pct_chg", e.target.value)}
                    />
                  </label>
                  {currentStrategyKey === "musecat_v1" ? (
                    <>
                      <label className="field">
                        <span>musecat_factor_weights.momentum</span>
                        <small className="field-hint">MuseCat 权重：动量</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.musecat_factor_weights_momentum}
                          onChange={(e) => setParamValue("musecat_factor_weights_momentum", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>musecat_factor_weights.reversal</span>
                        <small className="field-hint">MuseCat 权重：均值回归</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.musecat_factor_weights_reversal}
                          onChange={(e) => setParamValue("musecat_factor_weights_reversal", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>musecat_factor_weights.quality</span>
                        <small className="field-hint">MuseCat 权重：质量</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.musecat_factor_weights_quality}
                          onChange={(e) => setParamValue("musecat_factor_weights_quality", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>musecat_factor_weights.liquidity</span>
                        <small className="field-hint">MuseCat 权重：流动性</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.musecat_factor_weights_liquidity}
                          onChange={(e) => setParamValue("musecat_factor_weights_liquidity", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>musecat_breakout_bonus</span>
                        <small className="field-hint">MuseCat 突破加分</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.musecat_breakout_bonus}
                          onChange={(e) => setParamValue("musecat_breakout_bonus", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>musecat_drawdown_penalty</span>
                        <small className="field-hint">MuseCat 回撤惩罚分</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.musecat_drawdown_penalty}
                          onChange={(e) => setParamValue("musecat_drawdown_penalty", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>musecat_macd_zero_axis_cross_bonus</span>
                        <small className="field-hint">MuseCat 零轴下金叉加分上限</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.musecat_macd_zero_axis_cross_bonus}
                          onChange={(e) => setParamValue("musecat_macd_zero_axis_cross_bonus", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>musecat_macd_zero_axis_depth_scale</span>
                        <small className="field-hint">零轴下深度尺度：MACD 达到该负值给满分（如 3 表示 -3 给满加分，-1 约 1/3）</small>
                        <input
                          type="number"
                          step="0.1"
                          value={paramsForm.musecat_macd_zero_axis_depth_scale}
                          onChange={(e) => setParamValue("musecat_macd_zero_axis_depth_scale", e.target.value)}
                        />
                      </label>
                    </>
                  ) : (
                    <>
                      <label className="field">
                        <span>factor_weights.stock_trend</span>
                        <small className="field-hint">评分权重：个股趋势</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.factor_weights_stock_trend}
                          onChange={(e) => setParamValue("factor_weights_stock_trend", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>factor_weights.sector_strength</span>
                        <small className="field-hint">评分权重：板块强度</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.factor_weights_sector_strength}
                          onChange={(e) => setParamValue("factor_weights_sector_strength", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>factor_weights.value_quality</span>
                        <small className="field-hint">评分权重：估值质量</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.factor_weights_value_quality}
                          onChange={(e) => setParamValue("factor_weights_value_quality", e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>factor_weights.liquidity_stability</span>
                        <small className="field-hint">评分权重：流动性稳定</small>
                        <input
                          type="number"
                          step="0.01"
                          value={paramsForm.factor_weights_liquidity_stability}
                          onChange={(e) => setParamValue("factor_weights_liquidity_stability", e.target.value)}
                        />
                      </label>
                    </>
                  )}
                  <label className="field">
                    <span>signal_store_topk</span>
                    <small className="field-hint">每日保存信号条数上限</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.signal_store_topk}
                      onChange={(e) => setParamValue("signal_store_topk", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>sector_source_weights.sw</span>
                    <small className="field-hint">申万强度权重</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.sector_source_weights_sw}
                      onChange={(e) => setParamValue("sector_source_weights_sw", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>sector_source_weights.ci</span>
                    <small className="field-hint">中信强度权重</small>
                    <input
                      type="number"
                      step="0.01"
                      value={paramsForm.sector_source_weights_ci}
                      onChange={(e) => setParamValue("sector_source_weights_ci", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_daily_buy_count</span>
                    <small className="field-hint">单日最多买入笔数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_daily_buy_count}
                      onChange={(e) => setParamValue("max_daily_buy_count", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_daily_sell_count</span>
                    <small className="field-hint">单日最多卖出笔数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_daily_sell_count}
                      onChange={(e) => setParamValue("max_daily_sell_count", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_daily_trade_count</span>
                    <small className="field-hint">单日最多总交易笔数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_daily_trade_count}
                      onChange={(e) => setParamValue("max_daily_trade_count", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_daily_rotate_count</span>
                    <small className="field-hint">单日最多换仓次数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_daily_rotate_count}
                      onChange={(e) => setParamValue("max_daily_rotate_count", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>reentry_cooldown_days</span>
                    <small className="field-hint">卖出后冷却天数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.reentry_cooldown_days}
                      onChange={(e) => setParamValue("reentry_cooldown_days", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>annual_trade_window_days</span>
                    <small className="field-hint">滚动窗口交易日数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.annual_trade_window_days}
                      onChange={(e) => setParamValue("annual_trade_window_days", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_annual_trade_count</span>
                    <small className="field-hint">窗口内最多总交易笔数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_annual_trade_count}
                      onChange={(e) => setParamValue("max_annual_trade_count", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_annual_buy_count</span>
                    <small className="field-hint">窗口内最多买入笔数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_annual_buy_count}
                      onChange={(e) => setParamValue("max_annual_buy_count", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>max_annual_sell_count</span>
                    <small className="field-hint">窗口内最多卖出笔数</small>
                    <input
                      type="number"
                      step="1"
                      value={paramsForm.max_annual_sell_count}
                      onChange={(e) => setParamValue("max_annual_sell_count", e.target.value)}
                    />
                  </label>
                  <label className="field checkbox-field">
                    <input
                      type="checkbox"
                      checked={paramsForm.enable_buy_tech_filter}
                      onChange={(e) => setParamValue("enable_buy_tech_filter", e.target.checked)}
                    />
                    <div>
                      <span>enable_buy_tech_filter</span>
                      <small className="field-hint">是否启用买入技术面过滤</small>
                    </div>
                  </label>
                  <label className="field checkbox-field">
                    <input
                      type="checkbox"
                      checked={paramsForm.allow_buy_in_risk_off}
                      onChange={(e) => setParamValue("allow_buy_in_risk_off", e.target.checked)}
                    />
                    <div>
                      <span>allow_buy_in_risk_off</span>
                      <small className="field-hint">risk_off 阶段是否允许新开仓</small>
                    </div>
                  </label>
                  <label className="field checkbox-field">
                    <input
                      type="checkbox"
                      checked={paramsForm.entry_require_trend_alignment}
                      onChange={(e) => setParamValue("entry_require_trend_alignment", e.target.checked)}
                    />
                    <div>
                      <span>entry_require_trend_alignment</span>
                      <small className="field-hint">入场要求 close&gt;ma20&gt;ma60</small>
                    </div>
                  </label>
                  <label className="field checkbox-field">
                    <input
                      type="checkbox"
                      checked={paramsForm.entry_require_macd_positive}
                      onChange={(e) => setParamValue("entry_require_macd_positive", e.target.checked)}
                    />
                    <div>
                      <span>entry_require_macd_positive</span>
                      <small className="field-hint">入场要求 MACD 柱线为正</small>
                    </div>
                  </label>
                  <label className="field checkbox-field">
                    <input
                      type="checkbox"
                      checked={paramsForm.entry_require_macd_zero_axis_cross}
                      onChange={(e) => setParamValue("entry_require_macd_zero_axis_cross", e.target.checked)}
                    />
                    <div>
                      <span>entry_require_macd_zero_axis_cross</span>
                      <small className="field-hint">入场要求零轴下金叉（macd_hist&gt;0 且 DIF/DEA&lt;0）</small>
                    </div>
                  </label>
                  <label className="field checkbox-field">
                    <input
                      type="checkbox"
                      checked={paramsForm.use_member_sector_mapping}
                      onChange={(e) => setParamValue("use_member_sector_mapping", e.target.checked)}
                    />
                    <div>
                      <span>use_member_sector_mapping</span>
                      <small className="field-hint">优先按成分映射行业强度</small>
                    </div>
                  </label>
                </div>

                <div className="board-options">
                  <div className="board-options-title">allowed_boards</div>
                  <div className="board-options-grid">
                    {BOARD_OPTIONS.map((item) => (
                      <label key={item.value} className="board-option-item">
                        <input
                          type="checkbox"
                          checked={Boolean(paramsForm[`allowed_boards_${item.value}`])}
                          onChange={(e) => setParamValue(`allowed_boards_${item.value}`, e.target.checked)}
                        />
                        <span>{item.label}</span>
                      </label>
                    ))}
                  </div>
                </div>

                </div>

                <aside className="version-json-panel">
                  <div className="version-json-header">
                    <span className="version-json-title">params_snapshot (JSON)</span>
                    <span className="version-json-tip">提交以右侧 JSON 为准</span>
                  </div>
                  <textarea
                    className="version-json-textarea"
                    value={paramsJsonText}
                    onChange={(e) => handleParamsJsonChange(e.target.value)}
                    spellCheck={false}
                  />
                  {paramsJsonError ? <div className="version-json-error">{paramsJsonError}</div> : null}
                  <div className="form-actions version-submit-row" style={{ marginTop: 12 }}>
                    <button className="primary" type="submit">
                      发布版本
                    </button>
                  </div>
                </aside>
                </div>
                  </form>
                ) : (
                  <div className="empty">请先在左侧选择策略</div>
                )}
              </div>
            </div>
          ) : null}
        </section>
        )}

        <section className="strategy-column strategy-column--runs">
          <section className="panel">
            <h3 style={{ marginTop: 0 }}>创建回测</h3>
            {selectedStrategyId ? (
              <form className="form-grid" onSubmit={createRunMeta}>
                <label className="field">
                  <span>版本</span>
                  <select value={selectedVersionId} onChange={(e) => setSelectedVersionId(e.target.value)} required>
                    <option value="">请选择版本</option>
                    {versions.map((item) => (
                      <option key={item.strategy_version_id} value={item.strategy_version_id}>
                        {item.version} ({item.strategy_version_id})
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Run Type</span>
                  <select value={runType} onChange={(e) => setRunType(e.target.value)}>
                    <option value="range">range</option>
                    <option value="full_history">full_history</option>
                  </select>
                </label>
                <label className="field">
                  <span>开始日期</span>
                  <input value={runStartDate} onChange={(e) => setRunStartDate(e.target.value)} required />
                </label>
                <label className="field">
                  <span>结束日期</span>
                  <input value={runEndDate} onChange={(e) => setRunEndDate(e.target.value)} required />
                </label>
                <div className="form-actions">
                  <button className="primary" type="submit" disabled={runCreating || !selectedVersionId}>
                    {runCreating ? "创建中..." : "创建回测元信息"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="empty">请先在左侧选择策略</div>
            )}
          </section>

          <section className="panel">
            <div className="panel-title-row">
              <h3 style={{ margin: 0 }}>回测列表</h3>
              <span className="subtitle" style={{ margin: 0 }}>
                当前策略: {selectedStrategyId || "-"}
              </span>
            </div>
            {selectedStrategyId ? (
              <>
                <div className="table-wrap compact-table" style={{ marginTop: 12 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>对比</th>
                        <th>Run ID</th>
                        <th>版本</th>
                        <th>状态</th>
                        <th>区间</th>
                        <th>累计收益</th>
                        <th>创建时间</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="empty">
                            暂无回测记录
                          </td>
                        </tr>
                      ) : (
                        runs.map((item) => (
                          <tr key={item.run_id}>
                            <td>
                              <input
                                type="checkbox"
                                checked={selectedRunIds.includes(item.run_id)}
                                onChange={(e) => toggleRunSelect(item.run_id, e.target.checked)}
                              />
                            </td>
                            <td>
                              <Link className="link-button" href={`/backtests/${item.run_id}`}>
                                {item.run_id}
                              </Link>
                            </td>
                            <td>{item.strategy_version_id}</td>
                            <td>{item.status}</td>
                            <td>
                              {item.start_date} ~ {item.end_date}
                            </td>
                            <td>{formatPct(item?.summary_metrics?.total_return)}</td>
                            <td>{formatDateTime(item.created_at)}</td>
                            <td>
                              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                <button type="button" className="link-button" onClick={() => showRunParams(item)}>
                                  参数
                                </button>
                                <button
                                  type="button"
                                  className="danger-button"
                                  onClick={() => deleteRun(item.run_id)}
                                  disabled={deletingRunId === item.run_id || item.status === "running"}
                                >
                                  {deletingRunId === item.run_id ? "删除中..." : "删除"}
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                <div style={{ marginTop: 12 }}>
                  <button className="primary" type="button" disabled={selectedRunIds.length < 2} onClick={goCompare}>
                    对比已选 Run（{selectedRunIds.length}/5）
                  </button>
                </div>
              </>
            ) : (
              <div className="empty" style={{ marginTop: 12 }}>
                请先在左侧选择策略
              </div>
            )}
          </section>
        </section>
      </div>

      {strategyModalOpen ? (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeStrategyModal();
          }}
        >
          <div className="modal-card modal-card--strategy-create">
            <div className="modal-header">
              <h3 style={{ margin: 0 }}>创建策略</h3>
              <button type="button" className="link-button" onClick={closeStrategyModal}>
                关闭
              </button>
            </div>
            <form className="form-grid" onSubmit={createStrategy}>
              <label className="field">
                <span>名称</span>
                <input value={newName} onChange={(e) => setNewName(e.target.value)} required />
              </label>
              <label className="field">
                <span>策略键</span>
                <select value={newStrategyKey} onChange={(e) => setNewStrategyKey(resolveStrategyKey(e.target.value))}>
                  {STRATEGY_KEY_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Owner</span>
                <input value={newOwner} onChange={(e) => setNewOwner(e.target.value)} />
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span>描述</span>
                <input value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
              </label>
              <div className="form-actions">
                <button className="primary" type="submit" disabled={loading || !newName.trim()}>
                  新建策略
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {paramsModalRun ? (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeRunParams();
          }}
        >
          <div className="modal-card">
            <div className="modal-header">
              <h3 style={{ margin: 0 }}>Run 参数快照</h3>
              <button type="button" className="link-button" onClick={closeRunParams}>
                关闭
              </button>
            </div>
            <div className="subtitle" style={{ marginBottom: 8 }}>
              {paramsModalRun.run_id}
            </div>
            <pre className="params-json">{JSON.stringify(paramsModalRun.params_snapshot || {}, null, 2)}</pre>
          </div>
        </div>
      ) : null}
    </main>
  );
}
