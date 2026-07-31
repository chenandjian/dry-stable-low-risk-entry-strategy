<template>
  <div class="page-content">
    <div class="page-heading">
      <span class="terminal-kicker">STRATEGY 6 / CONTROL PARAMETERS</span>
      <h2 class="page-title">策略配置</h2>
      <p class="page-sub">策略6扫描、行情数据与定时任务参数，保存后立即生效</p>
    </div>

    <!-- 市场范围 -->
    <section class="section">
      <h3 class="section-title">市场范围</h3>
      <div class="toggle-grid">
        <label v-for="m in markets" :key="m.key" class="toggle-item">
          <span class="toggle-label" :title="m.tip">{{ m.label }}</span>
          <button class="toggle" :class="{ active: config.market?.[m.key] }"
            @click="toggle('market', m.key)">{{ config.market?.[m.key] ? '开' : '关' }}</button>
        </label>
      </div>
    </section>

    <!-- 基础参数 -->
    <section class="section">
      <h3 class="section-title">行情数据</h3>
      <div v-if="false" class="param-grid">
        <div class="param">
          <label title="近20日平均成交额低于此值的股票将被过滤（单位：元）">平均成交额阈值 <span class="unit">元</span></label>
          <input type="number" v-model.number="config.liquidity.min_avg_turnover"
            @input="markDirty" step="1000000" />
          <span class="default">默认 1亿</span>
        </div>
        <div class="param">
          <label title="股价低于此值的股票将被过滤（单位：元）">最低股价 <span class="unit">元</span></label>
          <input type="number" v-model.number="config.liquidity.min_stock_price"
            @input="markDirty" step="1" min="0" />
          <span class="default">默认 10元</span>
        </div>
        <div class="param">
          <label title="每只股票拉取的日线数量，低于此天数的股票自动过滤">日线拉取天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.liquidity.min_listing_days"
            @input="markDirty" step="10" min="30" />
          <span class="default">默认 250天</span>
        </div>
        <div class="param">
          <label title="扫描时传入统一策略引擎的最近交易日数量，用于杯柄/VCP形态检测和干稳低吸分析">扫描分析天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.data.scan_window_days"
            @input="markDirty" step="50" min="30" />
          <span class="default">默认 250天</span>
        </div>
        <div class="param">
          <label title="回测时每次形态分析使用的交易日数，逐日滑动评估历史数据中的每个交易日">回测分析天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.data.backtest_window_days"
            @input="markDirty" step="50" min="30" />
          <span class="default">默认 250天</span>
        </div>
      </div>
      <div class="param-group" style="margin-top:12px">
        <label class="param-label">日线数据获取模式</label>
        <div class="mode-options">
          <label class="mode-option">
            <input data-test="acquisition-mode-tickflow" type="radio"
              v-model="config.data.acquisition_mode" value="tickflow" @change="markDirty" />
            <span><strong>TickFlow 批量模式</strong><small>正式模式，股票使用前复权批量日线；失败时不会自动切换传统数据源。</small></span>
          </label>
          <label class="mode-option">
            <input data-test="acquisition-mode-legacy" type="radio"
              v-model="config.data.acquisition_mode" value="legacy_multi_source" @change="markDirty" />
            <span><strong>传统多数据源模式</strong><small>人工备用模式，按下方启用顺序调用腾讯、AkShare-Sina、百度。</small></span>
          </label>
        </div>
      </div>
      <div class="param-group" style="margin-top:12px">
        <label class="param-label">TickFlow 访问模式</label>
        <div class="mode-options">
          <label class="mode-option">
            <input data-test="tickflow-access-free" type="radio"
              v-model="config.data.tickflow_access_mode" value="free" @change="markDirty" />
            <span><strong>免费模式（默认）</strong><small>始终调用 TickFlow.free()，不会使用已保存的 API Key。</small></span>
          </label>
          <label class="mode-option">
            <input data-test="tickflow-access-authenticated" type="radio"
              v-model="config.data.tickflow_access_mode" value="authenticated" @change="markDirty" />
            <span><strong>API Key 认证模式</strong><small>只使用 API Key 认证，失败时不会自动切换免费模式。</small></span>
          </label>
        </div>
        <p v-if="config.data.tickflow_access_mode === 'free'" class="section-hint">
          已保存的 Key 会保留，但当前不会使用。
        </p>
      </div>
      <div v-if="config.data.tickflow_access_mode === 'authenticated'"
        class="param-group tickflow-key-group" style="margin-top:12px">
        <label class="param-label" for="tickflow-api-key">
          TickFlow API Key
          <span class="key-status" :class="{ configured: config.data.tickflow_api_key_configured }">
            {{ config.data.tickflow_api_key_configured ? '已配置' : '未配置' }}
          </span>
        </label>
        <div class="secret-input-row">
          <input id="tickflow-api-key" data-test="tickflow-api-key"
            :type="showTickFlowApiKey ? 'text' : 'password'"
            v-model="config.data.tickflow_api_key"
            autocomplete="new-password"
            placeholder="留空表示保留现有密钥"
            @input="markDirty" />
          <button type="button" class="btn-secondary" data-test="tickflow-api-key-visible"
            @click="showTickFlowApiKey = !showTickFlowApiKey">
            {{ showTickFlowApiKey ? '隐藏' : '显示' }}
          </button>
        </div>
        <p class="section-hint">后端不会回显已保存的密钥；输入新值并保存才会替换，留空会保留原值。</p>
      </div>
      <div class="param-group" style="margin-top:12px">
        <label class="param-label" title="按优先级排列，首位为主数据源，拉取失败时按顺序尝试后续数据源">日线数据源 <span class="unit">按优先级排列</span></label>
        <div class="toggle-grid">
          <label v-for="src in availableSources" :key="src.key" class="toggle-item">
            <span class="toggle-label" :title="src.tip">{{ src.label }}</span>
            <button class="toggle" :class="{ active: (config.data.daily_sources || []).includes(src.key) }"
              @click="toggleSource(src.key)">{{ (config.data.daily_sources || []).includes(src.key) ? '开' : '关' }}</button>
          </label>
        </div>
      </div>
    </section>

    <!-- 定时任务 -->
    <section class="section scheduler-section">
      <h3 class="section-title">定时任务</h3>
      <p class="section-hint">
        工作日按设定时间执行策略6全市场扫描。保存后会立即重载后端定时任务。
      </p>
      <div class="toggle-grid" style="margin-bottom:16px">
        <label class="toggle-item">
          <span class="toggle-label">启用定时任务</span>
          <button data-test="scheduler-enabled" class="toggle" :class="{ active: config.scheduler?.enabled === true }"
            @click="toggleScheduler('enabled')">{{ config.scheduler?.enabled === true ? '开' : '关' }}</button>
        </label>
      </div>
      <div class="param-grid">
        <div class="param">
          <label title="仅支持周一至周五固定时间执行">执行时间 <span class="unit">周一至周五</span></label>
          <input data-test="scheduler-time" type="time" v-model="serialDualScanTime" @input="markDirty" />
          <span class="default">当前 cron: {{ config.scheduler?.serial_dual_scan?.cron || '--' }}</span>
        </div>
      </div>
    </section>

    <!-- 高级参数 -->
    <section v-if="false" class="section">
      <h3 class="section-title" style="cursor:pointer" @click="showAdvanced = !showAdvanced">
        {{ showAdvanced ? '▾' : '▸' }} 高级参数
      </h3>
      <div v-if="showAdvanced">
        <h4 class="sub-group-title">流动性</h4>
        <div class="param-grid">
          <div class="param">
            <label title="近20日平均成交量低于此值的股票将被过滤（单位：股）">平均成交量阈值 <span class="unit">股</span></label>
            <input type="number" v-model.number="config.liquidity.min_avg_volume"
              @input="markDirty" step="100000" />
            <span class="default">默认 500万</span>
          </div>
          <div class="param">
            <label title="最近交易日成交额低于此值的股票将被过滤（单位：元）">最新成交额阈值 <span class="unit">元</span></label>
            <input type="number" v-model.number="config.liquidity.min_latest_turnover"
              @input="markDirty" step="1000000" />
            <span class="default">默认 8000万</span>
          </div>
        </div>

        <h4 class="sub-group-title">杯体结构</h4>
        <div class="param-grid">
          <div class="param">
            <label title="杯体从杯口到杯底再到杯口的最短交易日数">最短周期 <span class="unit">交易日</span></label>
            <input type="range" min="20" max="60" v-model.number="config.cup.min_duration" @input="markDirty" />
            <div class="range-val">{{ config.cup.min_duration }} 天</div>
          </div>
          <div class="param">
            <label title="杯体从杯口到杯底再到杯口的最长交易日数">最长周期 <span class="unit">交易日</span></label>
            <input type="range" min="100" max="250" v-model.number="config.cup.max_duration" @input="markDirty" />
            <div class="range-val">{{ config.cup.max_duration }} 天</div>
          </div>
          <div class="param">
            <label title="杯体回调的最小幅度，低于此幅度不算杯体">最小深度 <span class="unit">%</span></label>
            <input type="range" min="5" max="20" step="1" v-model.number="cupMinDepth" @input="markDirty" />
            <div class="range-val">{{ cupMinDepth }}%</div>
          </div>
          <div class="param">
            <label title="杯体回调的最大幅度，超过此幅度杯体太深">最大深度 <span class="unit">%</span></label>
            <input type="range" min="30" max="55" step="1" v-model.number="cupMaxDepth" @input="markDirty" />
            <div class="range-val">{{ cupMaxDepth }}%</div>
          </div>
          <div class="param">
            <label title="左右杯口价格的最大偏差比例">杯口最大偏差 <span class="unit">%</span></label>
            <input type="range" min="5" max="20" step="1" v-model.number="cupLipDeviation" @input="markDirty" />
            <div class="range-val">{{ cupLipDeviation }}%</div>
          </div>
          <div class="param">
            <label title="杯底附近价格在杯底8%范围内的比例阈值">杯底圆滑度 <span class="unit">%</span></label>
            <input type="range" min="5" max="30" step="1" v-model.number="cupRoundness" @input="markDirty" />
            <div class="range-val">{{ cupRoundness }}%</div>
          </div>
        </div>

        <h4 class="sub-group-title">柄部结构</h4>
        <div class="param-grid">
          <div class="param">
            <label title="柄部回调的最短交易日数">最短周期 <span class="unit">交易日</span></label>
            <input type="range" min="3" max="10" v-model.number="handleMinDur" @input="markDirty" />
            <div class="range-val">{{ handleMinDur }} 天</div>
          </div>
          <div class="param">
            <label title="柄部回调的最长交易日数">最长周期 <span class="unit">交易日</span></label>
            <input type="range" min="20" max="40" v-model.number="handleMaxDur" @input="markDirty" />
            <div class="range-val">{{ handleMaxDur }} 天</div>
          </div>
          <div class="param">
            <label title="柄部从右杯口向下的最大回撤幅度">最大回撤 <span class="unit">%</span></label>
            <input type="range" min="8" max="25" step="1" v-model.number="handleMaxDepth" @input="markDirty" />
            <div class="range-val">{{ handleMaxDepth }}%</div>
          </div>
        </div>

        <h4 class="sub-group-title">突破判断</h4>
        <div class="param-grid">
          <div class="param">
            <label title="突破确认的价格缓冲比例，超过杯口此比例算突破">缓冲比例 <span class="unit">%</span></label>
            <input type="range" min="0" max="5" step="0.5" v-model.number="breakoutBuffer" @input="markDirty" />
            <div class="range-val">{{ breakoutBuffer }}%</div>
          </div>
          <div class="param">
            <label title="突破当天成交量相对均量的倍数阈值">放量倍数</label>
            <input type="range" min="1.0" max="2.5" step="0.1" v-model.number="config.breakout.volume_multiplier" @input="markDirty" />
            <div class="range-val">{{ config.breakout.volume_multiplier }}×</div>
          </div>
        </div>

        <h4 class="sub-group-title">决策规则</h4>
        <div class="param-grid">
          <div class="param">
            <label title="止损空间超过此值直接拒绝买入">止损空间上限 <span class="unit">%</span></label>
            <input type="range" min="5" max="15" step="0.5" v-model.number="maxRiskPercent" @input="markDirty" />
            <div class="range-val">{{ maxRiskPercent }}%</div>
          </div>
          <div class="param">
            <label title="量干评分低于此值直接拒绝（满分12）">量干最低分</label>
            <input type="range" min="4" max="10" v-model.number="config.decision.min_volume_dry_score" @input="markDirty" />
            <div class="range-val">{{ config.decision.min_volume_dry_score }} 分</div>
          </div>
          <div class="param">
            <label title="价稳评分低于此值直接拒绝">价稳最低分</label>
            <input type="range" min="3" max="8" v-model.number="config.decision.min_price_stable_score" @input="markDirty" />
            <div class="range-val">{{ config.decision.min_price_stable_score }} 分</div>
          </div>
          <div class="param">
            <label title="形态评分低于此值直接拒绝">形态最低分</label>
            <input type="range" min="5" max="12" v-model.number="config.decision.min_pattern_score" @input="markDirty" />
            <div class="range-val">{{ config.decision.min_pattern_score }} 分</div>
          </div>
          <div class="param">
            <label title="第一目标盈亏比低于此值直接拒绝">盈亏比下限</label>
            <input type="range" min="1.0" max="3.0" step="0.1" v-model.number="config.decision.min_rr1" @input="markDirty" />
            <div class="range-val">{{ config.decision.min_rr1 }} : 1</div>
          </div>
          <div class="param">
            <label title="可低吸额外要求：止损空间上限">可低吸止损上限 <span class="unit">%</span></label>
            <input type="range" min="3" max="10" step="0.5" v-model.number="config.decision.low_buy_max_risk_percent" @input="markDirty" />
            <div class="range-val">{{ config.decision.low_buy_max_risk_percent }}%</div>
          </div>
        </div>

        <h4 class="sub-group-title">量干进阶</h4>
        <div class="param-grid">
          <div class="param">
            <label title="近10日价格线性回归斜率低于此值且收盘低于MA20时，量干最高分被限制">缩量阴跌封顶分</label>
            <input type="range" min="5" max="10" v-model.number="config.volume_dry.bad_shrink_max_score" @input="markDirty" />
            <div class="range-val">{{ config.volume_dry.bad_shrink_max_score }} 分</div>
          </div>
          <div class="param">
            <label title="股价处于近60日区间下半部时量干最高分">低位缩量封顶分</label>
            <input type="range" min="5" max="10" v-model.number="config.volume_dry.low_position_max_score" @input="markDirty" />
            <div class="range-val">{{ config.volume_dry.low_position_max_score }} 分</div>
          </div>
          <div class="param">
            <label title="近5天放量但不涨时量干最高分">放量滞涨封顶分</label>
            <input type="range" min="5" max="10" v-model.number="config.volume_dry.volume_stall_max_score" @input="markDirty" />
            <div class="range-val">{{ config.volume_dry.volume_stall_max_score }} 分</div>
          </div>
          <div class="param">
            <label title="近3天放量大阴线时量干最高分">大阴线封顶分</label>
            <input type="range" min="4" max="9" v-model.number="config.volume_dry.big_bear_max_score" @input="markDirty" />
            <div class="range-val">{{ config.volume_dry.big_bear_max_score }} 分</div>
          </div>
        </div>

        <h4 class="sub-group-title">价稳进阶</h4>
        <div class="param-grid">
          <div class="param">
            <label title="近5日收盘价波动≤此值视为价格紧致">收盘紧致度 <span class="unit">%</span></label>
            <input type="range" min="1" max="8" v-model.number="config.price_stable.close_tightness_strong_pct" @input="markDirty" />
            <div class="range-val">{{ config.price_stable.close_tightness_strong_pct }}%</div>
          </div>
          <div class="param">
            <label title="跌破柄底/MA50时价稳最高分">支撑跌破封顶分</label>
            <input type="range" min="3" max="7" v-model.number="config.price_stable.support_break_max_score" @input="markDirty" />
            <div class="range-val">{{ config.price_stable.support_break_max_score }} 分</div>
          </div>
        </div>

        <h4 class="sub-group-title">风报进阶</h4>
        <div class="param-grid">
          <div class="param">
            <label title="止损空间必须≥ATR14×此倍数，否则发出警告">ATR止损倍数</label>
            <input type="range" min="1.0" max="2.0" step="0.1" v-model.number="config.risk_reward.atr_stop_multiplier" @input="markDirty" />
            <div class="range-val">{{ config.risk_reward.atr_stop_multiplier }}×</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 策略2：极致量干价稳 -->
    <section v-if="false" class="section strategy2-section">
      <h3 class="section-title strategy2-title">策略2 · 极致量干价稳</h3>
      <p class="section-hint">
        策略2 独立扫描全部股票，不依赖杯柄/VCP 形态识别。日线拉取天数沿用全局配置；本期不支持回测。
      </p>

      <!-- 启停开关 -->
      <div class="toggle-grid" style="margin-bottom:16px">
        <label class="toggle-item">
          <span class="toggle-label">启用策略2</span>
          <button class="toggle" :class="{ active: config.strategy2?.enabled !== false }"
            @click="toggleStrategy2('enabled')">{{ config.strategy2?.enabled !== false ? '开' : '关' }}</button>
        </label>
      </div>

      <div class="param-grid">
        <div class="param">
          <label title="策略2计算仅使用最近 N 个有效交易日的数据">策略计算天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy2.strategy_window_days"
            @input="markDirty" step="10" min="60" />
          <span class="default">默认 120 · 须 ≥ 最低有效数据天数</span>
        </div>
        <div class="param">
          <label title="有效数据不足此天数时跳过该股票">最低有效数据天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy2.minimum_required_days"
            @input="markDirty" step="5" min="60" />
          <span class="default">默认 60 · ≥ 60</span>
        </div>
        <div class="param">
          <label title="总分 ≥ 此值且无否决且风险比达标才入选">候选最低分</label>
          <input type="number" v-model.number="config.strategy2.candidate_min_score"
            @input="markDirty" min="0" max="100" />
          <span class="default">默认 70 · 0-100</span>
        </div>
        <div class="param">
          <label title="量干评分低于此值时，即使总分达标也不进入策略2正式候选">正式量干最低分</label>
          <input type="number" v-model.number="config.strategy2.minimum_volume_dry_score"
            @input="markDirty" min="0" max="100" />
          <span class="default">优化后 40 · 0-100</span>
        </div>
        <div class="param">
          <label title="短线观察建议退出天数，仅用于候选展示和策略说明，不改变入选硬过滤">短线退出建议 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy2.short_term_time_exit_days"
            @input="markDirty" min="0" max="20" />
          <span class="default">优化后 5 · 0 表示关闭</span>
        </div>
        <div class="param">
          <label title="风险比超过此值强制排除。风险比 = (收盘价 - 止损) / 收盘价">最大风险比 <span class="unit">%</span></label>
          <input type="range" min="1" max="10" step="0.5" v-model.number="maxRiskRatioPct" @input="markDirty" />
          <div class="range-val">{{ maxRiskRatioPct }}%</div>
        </div>
        <div class="param">
          <label title="关键支撑 = 不含评估日的前 N 个交易日最低收盘价">支撑回看天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy2.support_lookback_days"
            @input="markDirty" min="2" />
          <span class="default">默认 10 · ≥ 2</span>
        </div>
        <div class="param">
          <label title="买入区间上限 = 关键支撑 × (1 + 溢价比例)">买入区间溢价 <span class="unit">%</span></label>
          <input type="range" min="1" max="10" step="0.5" v-model.number="buyZonePremiumPct" @input="markDirty" />
          <div class="range-val">{{ buyZonePremiumPct }}%</div>
        </div>
        <div class="param">
          <label title="止损价 = 关键支撑 × (1 - 缓冲比例)">止损缓冲比例 <span class="unit">%</span></label>
          <input type="range" min="1" max="10" step="0.5" v-model.number="stopLossBufferPct" @input="markDirty" />
          <div class="range-val">{{ stopLossBufferPct }}%</div>
        </div>
      </div>

      <div class="info-msg">
        ⓘ 日线拉取天数使用全局配置 ({{ config.liquidity?.min_listing_days || '--' }} 天) · 策略2不使用杯柄/VCP判断 · 本期不支持回测
      </div>
    </section>

    <!-- 策略3：强势回踩二次启动 -->
    <section v-if="false" class="section strategy3-section">
      <h3 class="section-title strategy3-title">策略3 · 强势回踩二次启动</h3>
      <p class="section-hint">
        策略3不是杯柄/VCP策略，也不是极致量干价稳策略。它寻找已证明强势的股票，在健康回踩、缩量企稳后二次转强的机会。
      </p>

      <div class="toggle-grid" style="margin-bottom:16px">
        <label class="toggle-item">
          <span class="toggle-label">启用策略3</span>
          <button class="toggle" :class="{ active: config.strategy3?.enabled !== false }"
            @click="toggleStrategy3('enabled')">{{ config.strategy3?.enabled !== false ? '开' : '关' }}</button>
        </label>
      </div>

      <div class="param-grid">
        <div class="param">
          <label title="策略3计算仅使用最近 N 个有效交易日的数据">策略窗口天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy3.strategy_window_days" @input="markDirty" step="10" min="120" />
          <span class="default">默认 250 · 须 ≥ 最低有效数据天数</span>
        </div>
        <div class="param">
          <label title="有效数据不足此天数时跳过该股票">最低有效数据天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy3.minimum_required_days" @input="markDirty" step="10" min="120" />
          <span class="default">默认 180 · ≥ 120</span>
        </div>
        <div class="param">
          <label title="总分达到此值且无硬过滤才进入观察候选">候选最低分</label>
          <input type="number" v-model.number="config.strategy3.candidate_min_score" @input="markDirty" min="0" max="100" />
          <span class="default">默认 75 · 0-100</span>
        </div>
        <div class="param">
          <label title="总分达到此值标记为核心候选">核心候选最低分</label>
          <input type="number" v-model.number="config.strategy3.core_min_score" @input="markDirty" min="0" max="100" />
          <span class="default">默认 85 · ≥ 候选最低分</span>
        </div>
        <div class="param">
          <label title="风险比超过此值强制排除">最大风险比 <span class="unit">%</span></label>
          <input type="range" min="1" max="15" step="0.5" v-model.number="strategy3MaxRiskPct" @input="markDirty" />
          <div class="range-val">{{ strategy3MaxRiskPct }}%</div>
        </div>
        <div class="param">
          <label title="强势股回踩不足此幅度时视为偏追高">最小回踩幅度 <span class="unit">%</span></label>
          <input type="range" min="1" max="20" step="0.5" v-model.number="strategy3MinPullbackPct" @input="markDirty" />
          <div class="range-val">{{ strategy3MinPullbackPct }}%</div>
        </div>
        <div class="param">
          <label title="强势股回踩超过此幅度时视为趋势损坏风险">最大回踩幅度 <span class="unit">%</span></label>
          <input type="range" min="10" max="50" step="0.5" v-model.number="strategy3MaxPullbackPct" @input="markDirty" />
          <div class="range-val">{{ strategy3MaxPullbackPct }}%</div>
        </div>
        <div class="param">
          <label title="最近5日最大振幅超过此值强制排除">最大5日振幅 <span class="unit">%</span></label>
          <input type="range" min="3" max="25" step="0.5" v-model.number="strategy3MaxRange5Pct" @input="markDirty" />
          <div class="range-val">{{ strategy3MaxRange5Pct }}%</div>
        </div>
        <div class="param">
          <label title="最近3日涨幅超过此值视为短线过热">最大3日涨幅 <span class="unit">%</span></label>
          <input type="range" min="3" max="20" step="0.5" v-model.number="strategy3MaxSurge3Pct" @input="markDirty" />
          <div class="range-val">{{ strategy3MaxSurge3Pct }}%</div>
        </div>
        <div class="param">
          <label title="60日相对强度低于此值时排除">最低60日相对强度 <span class="unit">%</span></label>
          <input type="range" min="-10" max="30" step="0.5" v-model.number="strategy3MinRSPct" @input="markDirty" />
          <div class="range-val">{{ strategy3MinRSPct }}%</div>
        </div>
        <div class="param">
          <label title="V5/V20低于此值视为缩量企稳加分">缩量比例 V5/V20</label>
          <input type="range" min="0.3" max="1.5" step="0.05" v-model.number="config.strategy3.volume_shrink_ratio" @input="markDirty" />
          <div class="range-val">{{ config.strategy3.volume_shrink_ratio }}</div>
        </div>
      </div>

      <h4 class="sub-group-title">正式候选过滤</h4>
      <div class="param-grid">
        <div class="param">
          <label title="总分达到此值后才进入策略3正式候选；低于此值仅保留为诊断或审计">正式候选分数</label>
          <input data-test="strategy3-trade-score" type="number"
            v-model.number="config.strategy3.trade_candidate_min_score" @input="markDirty" min="0" max="100" />
          <span class="default">优化后 88 · ≥ 候选最低分</span>
        </div>
        <div class="param">
          <label title="正式候选风险比上限，风险比 = (当前价 - 止损价) / 当前价">正式最大风险 <span class="unit">%</span></label>
          <input data-test="strategy3-trade-risk" type="range" min="1" max="15" step="0.5"
            v-model.number="strategy3TradeMaxRiskPct" @input="markDirty" />
          <div class="range-val">{{ strategy3TradeMaxRiskPct }}%</div>
        </div>
        <div class="param">
          <label title="正式候选允许的最大回踩幅度；本轮回测采用 16%，避免 16.2% 以上连续亏损扩张">正式最大回撤 <span class="unit">%</span></label>
          <input data-test="strategy3-trade-pullback" type="range" min="10" max="50" step="0.5"
            v-model.number="strategy3TradeMaxPullbackPct" @input="markDirty" />
          <div class="range-val">{{ strategy3TradeMaxPullbackPct }}%</div>
        </div>
      </div>

      <div class="info-msg strategy3-info">
        ⓘ 日线拉取天数使用全局配置 ({{ config.liquidity?.min_listing_days || '--' }} 天) · 低优先级观察只进入审计/诊断，不进入正式候选列表
      </div>
    </section>

    <!-- 策略4：热点龙头二波 -->
    <section v-if="false" class="section strategy4-section">
      <h3 class="section-title strategy4-title">策略4 · 热点龙头二波</h3>
      <p class="section-hint">
        策略4先确认热点行业/题材，再识别核心龙头，最后只在龙头池中判断第一波回踩后的二波机会。
      </p>

      <div class="toggle-grid" style="margin-bottom:16px">
        <label class="toggle-item">
          <span class="toggle-label">启用策略4</span>
          <button class="toggle" :class="{ active: config.strategy4?.enabled !== false }"
            @click="toggleStrategy4('enabled')">{{ config.strategy4?.enabled !== false ? '开' : '关' }}</button>
        </label>
      </div>

      <div class="param-grid">
        <div class="param">
          <label title="热点题材正式榜最多保留数量">热点题材 Top N</label>
          <input type="number" v-model.number="config.strategy4.hot_topic_top_n" @input="markDirty" min="1" max="50" />
          <span class="default">默认 16</span>
        </div>
        <div class="param">
          <label title="热点观察榜最多保留数量，必须不小于热点题材 Top N">观察题材 Top N</label>
          <input type="number" v-model.number="config.strategy4.watch_hot_topic_top_n" @input="markDirty" min="1" max="100" />
          <span class="default">默认 16</span>
        </div>
        <div class="param">
          <label title="热点题材确认最低分">热点最低分</label>
          <input type="number" v-model.number="config.strategy4.min_hot_topic_score" @input="markDirty" min="0" max="100" />
          <span class="default">默认 65</span>
        </div>
        <div class="param">
          <label title="热点至少需要命中的强信号数量">热点强信号数</label>
          <input type="number" v-model.number="config.strategy4.min_hot_topic_signal_count" @input="markDirty" min="1" max="10" />
          <span class="default">默认 1</span>
        </div>
        <div class="param">
          <label title="每个热点最多保留的龙头股票数">每题材最多龙头</label>
          <input type="number" v-model.number="config.strategy4.max_total_leaders_per_topic" @input="markDirty" min="1" max="30" />
          <span class="default">默认 3</span>
        </div>
        <div class="param">
          <label title="龙头强度分低于该值不作为热点核心龙头">龙头强度最低分</label>
          <input type="number" v-model.number="config.strategy4.min_leader_strength_score" @input="markDirty" min="0" max="100" />
          <span class="default">默认 50</span>
        </div>
        <div class="param">
          <label title="健康回踩最小幅度">最小回踩 <span class="unit">%</span></label>
          <input type="range" min="1" max="30" step="0.5" v-model.number="strategy4PullbackMinPct" @input="markDirty" />
          <div class="range-val">{{ strategy4PullbackMinPct }}%</div>
        </div>
        <div class="param">
          <label title="健康回踩最大幅度">最大回踩 <span class="unit">%</span></label>
          <input type="range" min="5" max="50" step="0.5" v-model.number="strategy4PullbackMaxPct" @input="markDirty" />
          <div class="range-val">{{ strategy4PullbackMaxPct }}%</div>
        </div>
        <div class="param">
          <label title="非核心龙头最大风险比">最大风险比 <span class="unit">%</span></label>
          <input type="range" min="1" max="30" step="0.5" v-model.number="strategy4MaxRiskPct" @input="markDirty" />
          <div class="range-val">{{ strategy4MaxRiskPct }}%</div>
        </div>
        <div class="param">
          <label title="策略4最低预估收益风险比">最低收益风险比</label>
          <input type="number" v-model.number="config.strategy4.min_reward_risk_ratio" @input="markDirty" min="0.5" max="10" step="0.1" />
          <span class="default">默认 1.5</span>
        </div>
        <div class="param">
          <label title="启用后策略4会拉取真实行业/概念/板块指数K线，用于确认热点趋势">板块K线确认</label>
          <button class="toggle" :class="{ active: config.strategy4.topic_index?.enabled !== false }"
            @click="toggleStrategy4TopicIndex('enabled')">{{ config.strategy4.topic_index?.enabled !== false ? '开' : '关' }}</button>
          <span class="default">真实同花顺/东方财富板块K线</span>
        </div>
        <div class="param">
          <label title="正式二波候选必须具备可观察板块K线，否则只进入观察，不进入可买候选">正式候选要求板块K线</label>
          <button class="toggle" :class="{ active: config.strategy4.topic_index?.require_for_buyable_candidate !== false }"
            @click="toggleStrategy4TopicIndex('require_for_buyable_candidate')">{{ config.strategy4.topic_index?.require_for_buyable_candidate !== false ? '开' : '关' }}</button>
          <span class="default">默认开启，防止无板块历史仍出买点</span>
        </div>
        <div class="param">
          <label title="每个热点题材拉取的板块指数K线历史长度">板块K线历史 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy4.topic_index.history_days" @input="markDirty" min="60" max="1000" />
          <span class="default">默认 250</span>
        </div>
        <div class="param">
          <label title="低于该行数时，板块指数视为不可观察，不用于正式候选确认">最低板块K线行数</label>
          <input type="number" v-model.number="config.strategy4.topic_index.min_required_rows" @input="markDirty" min="2" max="500" />
          <span class="default">默认 60</span>
        </div>
      </div>

      <div class="info-msg strategy4-info">
        ⓘ 策略4不从全市场直接找形态，必须先过热点和龙头；正式候选默认必须有真实板块K线确认，缺失时标记不可观察。
      </div>
    </section>

    <!-- 策略5：短线强势冲刺盘整支撑 -->
    <section v-if="false" class="section strategy5-section">
      <h3 class="section-title strategy5-title">策略5 · 短线强势冲刺盘整支撑</h3>
      <p class="section-hint">
        策略5从全市场日线中寻找短线强度、新高确认、盘整可控且贴近 MA 支撑的重点/观察候选。
      </p>

      <div class="toggle-grid" style="margin-bottom:16px">
        <label class="toggle-item">
          <span class="toggle-label">启用策略5</span>
          <button class="toggle" :class="{ active: config.strategy5?.enabled !== false }"
            @click="toggleStrategy5('enabled')">{{ config.strategy5?.enabled !== false ? '开' : '关' }}</button>
        </label>
      </div>

      <div class="param-grid">
        <div class="param">
          <label title="策略5需要更长日线历史以计算 MA250 和长期交易日过滤">K线拉取天数</label>
          <input type="number" v-model.number="config.strategy5.kline_days" @input="markDirty" min="260" max="3000" />
          <span class="default">默认 1100</span>
        </div>
        <div class="param">
          <label title="F1：交易天数需要大于等于该阈值；最低 260 天用于保证 MA250 可计算">最低交易天数</label>
          <input type="number" v-model.number="config.strategy5.minimum_trading_days" @input="markDirty" min="260" max="3000" />
          <span class="default">默认 500 · ≥ 260</span>
        </div>
        <div class="param">
          <label title="F5：主板/创业板 60日均成交额，单位亿元">主创60日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy5.min_avg_amount_60d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 15</span>
        </div>
        <div class="param">
          <label title="F6：主板/创业板 30日均成交额，单位亿元">主创30日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy5.min_avg_amount_30d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 8</span>
        </div>
        <div class="param">
          <label title="F7：主板/创业板 10日均成交额，单位亿元">主创10日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy5.min_avg_amount_10d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 5</span>
        </div>
        <div class="param">
          <label title="科创板单独使用更高流动性门槛，减少低流动性科创股占比">科创60日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy5.kcb_min_avg_amount_60d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 50</span>
        </div>
        <div class="param">
          <label title="科创板单独使用更高流动性门槛，减少低流动性科创股占比">科创30日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy5.kcb_min_avg_amount_30d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 30</span>
        </div>
        <div class="param">
          <label title="科创板单独使用更高流动性门槛，减少低流动性科创股占比">科创10日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy5.kcb_min_avg_amount_10d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 20</span>
        </div>
        <div class="param">
          <label title="F8：20日短线强度阈值">20日强度</label>
          <input type="number" v-model.number="config.strategy5.strength_ret_20d" @input="markDirty" min="-1" max="5" step="0.01" />
          <span class="default">默认 0.20</span>
        </div>
        <div class="param">
          <label title="F8：10日短线强度阈值">10日强度</label>
          <input type="number" v-model.number="config.strategy5.strength_ret_10d" @input="markDirty" min="-1" max="5" step="0.01" />
          <span class="default">默认 0.12</span>
        </div>
        <div class="param">
          <label title="F8：5日短线强度阈值">5日强度</label>
          <input type="number" v-model.number="config.strategy5.strength_ret_5d" @input="markDirty" min="-1" max="5" step="0.01" />
          <span class="default">默认 0.08</span>
        </div>
        <div class="param">
          <label title="F9：近20日收盘高点接近120日高点比例">接近120日高比例</label>
          <input type="number" v-model.number="config.strategy5.near_120d_high_ratio" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.98</span>
        </div>
        <div class="param">
          <label title="F10：5日振幅超过该值直接排除">最大5日振幅</label>
          <input type="number" v-model.number="config.strategy5.max_amp_5d" @input="markDirty" min="0" max="2" step="0.01" />
          <span class="default">默认 0.22</span>
        </div>
        <div class="param">
          <label title="F10：10日振幅超过该值直接排除">最大10日振幅</label>
          <input type="number" v-model.number="config.strategy5.max_amp_10d" @input="markDirty" min="0" max="3" step="0.01" />
          <span class="default">默认 0.45</span>
        </div>
        <div class="param">
          <label title="重点候选最低支撑评分">重点候选支撑分</label>
          <input type="number" v-model.number="config.strategy5.key_candidate_min_support_score" @input="markDirty" min="0" max="10" />
          <span class="default">默认 8</span>
        </div>
        <div class="param">
          <label title="策略5量干评分达到该值，才允许进入重点候选">重点候选量干分</label>
          <input type="number" v-model.number="config.strategy5.volume_dry_min_score_key" @input="markDirty" min="0" max="20" />
          <span class="default">默认 14 · 满分20</span>
        </div>
        <div class="param">
          <label title="策略5量干评分达到该值，才允许进入观察候选">观察候选量干分</label>
          <input type="number" v-model.number="config.strategy5.volume_dry_min_score_watch" @input="markDirty" min="0" max="20" />
          <span class="default">默认 10 · 不高于重点候选</span>
        </div>
        <div class="param">
          <label title="正式交易候选最低总分；低于该分数只进入观察，不进入正式买入统计">正式候选最低分</label>
          <input type="number" v-model.number="config.strategy5.trade_candidate_min_score" @input="markDirty" min="0" max="100" step="1" />
          <span class="default">默认 68</span>
        </div>
        <div class="param">
          <label title="正式交易候选最低量干分；观察候选仍使用观察量干分">正式候选量干分</label>
          <input type="number" v-model.number="config.strategy5.trade_volume_dry_min_score" @input="markDirty" min="0" max="20" step="1" />
          <span class="default">默认 13 · 满分20</span>
        </div>
        <div class="param">
          <label title="正式候选短线加权分 = 总分×总分权重 + 短线强度分×短线权重">短线加权最低分</label>
          <input type="number" v-model.number="config.strategy5.trade_short_weighted_min_score" @input="markDirty" min="0" max="150" step="1" />
          <span class="default">默认 76</span>
        </div>
        <div class="param">
          <label title="正式候选短线加权分中的总分权重">总分权重</label>
          <input type="number" v-model.number="config.strategy5.trade_total_score_weight" @input="markDirty" min="0" max="2" step="0.05" />
          <span class="default">默认 0.75</span>
        </div>
        <div class="param">
          <label title="正式候选短线加权分中的短线强度权重">短线强度权重</label>
          <input type="number" v-model.number="config.strategy5.trade_short_strength_weight" @input="markDirty" min="0" max="5" step="0.05" />
          <span class="default">默认 1.25</span>
        </div>
        <div class="param">
          <label title="关闭时，MA5支撑只作为偏追高观察，不进入正式买入候选">正式允许MA5支撑</label>
          <button class="toggle" :class="{ active: config.strategy5.trade_allow_ma5_support === true }"
            @click="toggleStrategy5('trade_allow_ma5_support')">{{ config.strategy5.trade_allow_ma5_support === true ? '开' : '关' }}</button>
          <span class="default">默认关闭</span>
        </div>
      </div>

      <div class="info-msg strategy5-info">
        ⓘ 策略5继续使用 baidu / sina / tencent 日线链路；正式候选用于买入统计，观察候选只用于跟踪，不进入正式收益口径。
      </div>
    </section>

    <!-- 策略6：强势 VCP 尾部候选池 -->
    <section class="section strategy6-section">
      <h3 class="section-title strategy6-title">策略6 · 强势 VCP 尾部候选池</h3>
      <p class="section-hint">
        策略6独立寻找强势启动后的支撑横盘尾部，重点看价稳量干、支撑有效和 RR2 盈亏比。
      </p>
      <div data-test="strategy6-decision-profile" class="info-msg strategy6-info">
        当前决策规则：<strong>{{ config.strategy6?.decision_profile === 'research_quality_v2' ? '研究质量 V2' : '正式原始链' }}</strong>。
        稳定箱体、动态尾段、Brooks 与质量 V2 参数仅用于研究配置，正式原始链不读取这些参数作选股决策。
      </div>

      <div class="toggle-grid" style="margin-bottom:16px">
        <label class="toggle-item">
          <span class="toggle-label">启用策略6</span>
          <button class="toggle" :class="{ active: config.strategy6?.enabled !== false }"
            @click="toggleStrategy6('enabled')">{{ config.strategy6?.enabled !== false ? '开' : '关' }}</button>
        </label>
        <label class="toggle-item">
          <span class="toggle-label" title="识别 VCP、杯柄和平台形态">形态识别</span>
          <button class="toggle" :class="{ active: config.strategy6?.pattern_filter_enabled === true }"
            @click="toggleStrategy6('pattern_filter_enabled')">{{ config.strategy6?.pattern_filter_enabled === true ? '开' : '关' }}</button>
        </label>
        <label class="toggle-item">
          <span class="toggle-label" title="开启后按过滤模式处理弱势市场和风险市场">市场过滤</span>
          <button class="toggle" :class="{ active: config.strategy6?.enable_market_filter === true }"
            @click="toggleStrategy6('enable_market_filter')">{{ config.strategy6?.enable_market_filter === true ? '开' : '关' }}</button>
        </label>
      </div>

      <div class="param-grid">
        <div class="param">
          <label title="策略6需要 MA250 和长期新高确认">K线拉取天数</label>
          <input type="number" v-model.number="config.strategy6.kline_days" @input="markDirty" min="260" max="3000" />
          <span class="default">默认 1100</span>
        </div>
        <div class="param">
          <label title="低于该交易日数时不参与策略6评估">最低交易天数</label>
          <input type="number" v-model.number="config.strategy6.minimum_trading_days" @input="markDirty" min="260" max="3000" />
          <span class="default">默认 500</span>
        </div>
        <div class="param">
          <label title="60日均成交额过滤，单位亿元">60日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy6.min_avg_amount_60d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 3</span>
        </div>
        <div class="param">
          <label title="30日均成交额过滤，单位亿元">30日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy6.min_avg_amount_30d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 5</span>
        </div>
        <div class="param">
          <label title="10日均成交额过滤，单位亿元">10日均额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy6.min_avg_amount_10d_yi" @input="markDirty" min="0" max="1000" step="1" />
          <span class="default">默认 5</span>
        </div>
        <div class="param">
          <label title="普通强势启动最低单日涨幅">普通启动涨幅</label>
          <input type="number" v-model.number="config.strategy6.normal_start_return" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.07</span>
        </div>
        <div class="param">
          <label title="普通强势启动最低量比">普通启动量比</label>
          <input type="number" v-model.number="config.strategy6.normal_start_volume_ratio" @input="markDirty" min="0" max="20" step="0.1" />
          <span class="default">默认 2.0</span>
        </div>
        <div class="param">
          <label title="普通强势启动最低单日成交额，单位亿元">普通启动成交额 <span class="unit">亿</span></label>
          <input type="number" v-model.number="config.strategy6.normal_start_min_amount_yi" @input="markDirty" min="0" max="1000" step="0.5" />
          <span class="default">默认 2</span>
        </div>
        <div class="param">
          <label title="启动日成交额在该股此前60日中的最低分位">启动成交额自身分位</label>
          <input type="number" v-model.number="config.strategy6.normal_start_self_amount_percentile" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.90</span>
        </div>
        <div class="param">
          <label title="近20日最高收盘接近120日高点的比例">接近120日高比例</label>
          <input type="number" v-model.number="config.strategy6.near_120d_high_ratio" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.98</span>
        </div>
        <div class="param">
          <label title="严格过滤：弱势市场不允许重点/就绪；降级处理：降为观察；仅调整评分：只扣风险分">市场过滤模式</label>
          <select data-test="strategy6-market-filter-mode" v-model="config.strategy6.market_filter_mode" @change="markDirty">
            <option value="strict">严格过滤</option>
            <option value="downgrade">降级处理</option>
            <option value="score_only">仅调整评分</option>
          </select>
          <span class="default">默认：降级处理</span>
        </div>
        <div class="param">
          <label title="个股20日涨幅相对沪深300的最低超额收益">最低RS20</label>
          <input type="number" v-model.number="config.strategy6.min_relative_strength_20" @input="markDirty" min="-1" max="1" step="0.01" />
          <span class="default">默认 0.10</span>
        </div>
        <div class="param">
          <label title="启动事件向前搜索的最大交易日数">启动回看天数</label>
          <input type="number" v-model.number="config.strategy6.start_lookback_days" @input="markDirty" min="20" max="250" />
          <span class="default">默认 60</span>
        </div>
        <div class="param">
          <label title="启动后不足该天数只进入‘强势启动已确认’观察状态">最小启动年龄</label>
          <input data-test="strategy6-start-age-min" type="number" v-model.number="config.strategy6.start_age_min_days" @input="markDirty" min="1" max="20" />
          <span class="default">默认 5</span>
        </div>
        <div class="param">
          <label title="超过该启动年龄不再视为当前事件">最大启动年龄</label>
          <input type="number" v-model.number="config.strategy6.start_age_max_days" @input="markDirty" min="5" max="250" />
          <span class="default">默认 60</span>
        </div>
        <div class="param">
          <label title="启动段之后、尾段之前的最少独立整理天数">最小整理天数</label>
          <input type="number" v-model.number="config.strategy6.consolidation_min_days" @input="markDirty" min="1" max="40" />
          <span class="default">默认 5</span>
        </div>
        <div class="param">
          <label title="独立整理段允许的最大天数">最大整理天数</label>
          <input type="number" v-model.number="config.strategy6.consolidation_max_days" @input="markDirty" min="5" max="120" />
          <span class="default">默认 40</span>
        </div>
        <div class="param">
          <label title="尾部量价评估窗口，不与前置20日基准重叠">尾段窗口</label>
          <input type="number" v-model.number="config.strategy6.tail_window_days" @input="markDirty" min="3" max="10" />
          <span class="default">默认 5</span>
        </div>
        <div class="param">
          <label title="严格过滤直接排除未知形态；降级处理将候选降级；仅调整评分只影响形态分">形态过滤模式</label>
          <select data-test="strategy6-pattern-mode" v-model="config.strategy6.pattern_filter_mode" @change="markDirty">
            <option value="strict">严格过滤</option>
            <option value="downgrade">降级处理</option>
            <option value="score_only">仅调整评分</option>
          </select>
          <span class="default">默认：仅调整评分</span>
        </div>
        <div class="param">
          <label title="信号价至少达到最后收缩上沿的该比例范围；高于突破枢轴的突破由生命周期规则判断">形态距突破枢轴最大下偏</label>
          <input data-test="strategy6-pattern-pivot-proximity" type="number" v-model.number="config.strategy6.pattern_pivot_proximity_pct" @input="markDirty" min="0.01" max="0.20" step="0.01" />
          <span class="default">默认 0.05</span>
        </div>
        <div class="param">
          <label title="当前价高于突破枢轴超过该比例时标记为‘涨幅已过度延伸’并排除追高">突破过度延伸比例</label>
          <input data-test="strategy6-breakout-extended-max" type="number" v-model.number="config.strategy6.breakout_extended_max_pct" @input="markDirty" min="0.01" max="0.30" step="0.01" />
          <span class="default">默认 0.08</span>
        </div>
        <div class="param">
          <label title="支撑候选价格聚为同一簇的最大价格比例">支撑簇价差</label>
          <input type="number" v-model.number="config.strategy6.support_cluster_price_pct" @input="markDirty" min="0" max="0.2" step="0.001" />
          <span class="default">默认 0.015</span>
        </div>
        <div class="param">
          <label title="VCP后一段振幅相对前一段的最大比例">VCP振幅收缩比</label>
          <input type="number" v-model.number="config.strategy6.vcp_contraction_range_ratio" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.90</span>
        </div>
        <div class="param">
          <label title="VCP后一段成交量相对前一段的最大比例">VCP量能收缩比</label>
          <input type="number" v-model.number="config.strategy6.vcp_contraction_volume_ratio" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.90</span>
        </div>
        <div class="param">
          <label title="第一轮完整收缩允许的最大振幅，超过后不视为健康VCP第一轮">VCP第一轮最大振幅</label>
          <input data-test="strategy6-vcp-first-max-range" type="number" v-model.number="config.strategy6.vcp_first_contraction_max_range" @input="markDirty" min="0.08" max="0.50" step="0.01" />
          <span class="default">默认 0.32</span>
        </div>
        <div class="param">
          <label title="低点后累计反弹至少达到该比例，才可能确认完整一轮">VCP有效反弹最小涨幅</label>
          <input data-test="strategy6-vcp-rebound-min" type="number" v-model.number="config.strategy6.vcp_rebound_min_pct" @input="markDirty" min="0.01" max="0.20" step="0.01" />
          <span class="default">默认 0.03</span>
        </div>
        <div class="param">
          <label title="普通反弹峰值至少需要经过的可见交易日，强势直接突破不受此限制">VCP反弹确认交易日</label>
          <input data-test="strategy6-vcp-rebound-confirm-days" type="number" v-model.number="config.strategy6.vcp_rebound_confirm_days" @input="markDirty" min="2" max="10" step="1" />
          <span class="default">默认 2</span>
        </div>
        <div class="param">
          <label title="后轮低点低于前轮低点且低于该比例时输出小幅下移风险提示">VCP低点下移提示比例</label>
          <input data-test="strategy6-vcp-low-warning-ratio" type="number" v-model.number="config.strategy6.vcp_low_warning_ratio" @input="markDirty" min="0.97" max="1" step="0.01" />
          <span class="default">默认 0.99</span>
        </div>
        <div class="param">
          <label title="历史正式候选日到当前VCP第一轮起点的收盘跌幅超过该比例时，旧资格失效">历史候选至VCP起点最大跌幅</label>
          <input data-test="strategy6-vcp-history-max-start-loss" type="number" v-model.number="config.strategy6.vcp_history_max_start_loss_pct" @input="markDirty" min="0.01" max="0.50" step="0.01" />
          <span class="default">默认 0.15</span>
        </div>
        <div class="param">
          <label title="历史正式候选日到当前VCP第一轮起点的滚动最高收盘最大回撤超过该比例时，旧资格失效">历史资格最大回撤</label>
          <input data-test="strategy6-vcp-history-max-drawdown" type="number" v-model.number="config.strategy6.vcp_history_max_drawdown_pct" @input="markDirty" min="0.01" max="0.50" step="0.01" />
          <span class="default">默认 0.20</span>
        </div>
        <div class="param">
          <label title="VCP起点连续满足收盘低于MA20且MA20低于MA50达到该天数时，旧资格失效">历史资格空头失效天数</label>
          <input data-test="strategy6-vcp-history-bearish-days" type="number" v-model.number="config.strategy6.vcp_history_bearish_trend_days" @input="markDirty" min="1" max="20" step="1" />
          <span class="default">默认 5</span>
        </div>
        <div class="param">
          <label title="杯柄形态允许的杯体最小深度">杯体最小深度</label>
          <input type="number" v-model.number="config.strategy6.cup_depth_min" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.12</span>
        </div>
        <div class="param">
          <label title="杯柄形态允许的杯体最大深度">杯体最大深度</label>
          <input type="number" v-model.number="config.strategy6.cup_depth_max" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.35</span>
        </div>
        <div class="param">
          <label title="平台形态允许的最大价格振幅">平台最大振幅</label>
          <input type="number" v-model.number="config.strategy6.platform_max_range" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.12</span>
        </div>
        <div class="param">
          <label title="支撑簇合并时的ATR容差倍数">支撑簇 ATR 倍数</label>
          <input type="number" v-model.number="config.strategy6.support_cluster_atr_multiplier" @input="markDirty" min="0" max="10" step="0.1" />
          <span class="default">默认 0.5</span>
        </div>
        <div class="param">
          <label title="支撑区最小宽度占当前价比例">支撑区价格宽度</label>
          <input type="number" v-model.number="config.strategy6.support_zone_price_pct" @input="markDirty" min="0" max="0.2" step="0.001" />
          <span class="default">默认 0.01</span>
        </div>
        <div class="param">
          <label title="支撑区宽度的ATR倍数">支撑区 ATR 倍数</label>
          <input type="number" v-model.number="config.strategy6.support_zone_atr_multiplier" @input="markDirty" min="0" max="10" step="0.1" />
          <span class="default">默认 0.3</span>
        </div>
        <div class="param">
          <label title="统计支撑测试次数的交易日窗口">支撑测试回看</label>
          <input type="number" v-model.number="config.strategy6.support_test_lookback" @input="markDirty" min="5" max="40" />
          <span class="default">默认 10</span>
        </div>
        <div class="param">
          <label title="止损位低于关键支撑的最小比例缓冲">止损支撑缓冲</label>
          <input type="number" v-model.number="config.strategy6.stop_key_support_pct" @input="markDirty" min="0" max="0.2" step="0.01" />
          <span class="default">默认 0.03</span>
        </div>
        <div class="param">
          <label title="止损缓冲取关键支撑比例和ATR缓冲的较大值">止损 ATR 倍数</label>
          <input data-test="strategy6-stop-atr-multiplier" type="number" v-model.number="config.strategy6.stop_atr_multiplier" @input="markDirty" min="0" max="10" step="0.1" />
          <span class="default">默认 0.8</span>
        </div>
        <div class="param">
          <label title="客观第二目标相对现价的最大上限">客观目标2上限</label>
          <input type="number" v-model.number="config.strategy6.target_2_cap_pct" @input="markDirty" min="0" max="2" step="0.01" />
          <span class="default">默认 0.35</span>
        </div>
        <div class="param">
          <label title="交易计划自信号日起可执行的交易日数">买入区有效天数</label>
          <input type="number" v-model.number="config.strategy6.buy_zone_valid_days" @input="markDirty" min="1" max="10" />
          <span class="default">默认 3</span>
        </div>
        <div class="param">
          <label title="同一启动事件在候选池中允许观察的最大交易日数">最大观察天数</label>
          <input data-test="strategy6-max-watch-days" type="number" v-model.number="config.strategy6.max_watch_days" @input="markDirty" min="1" max="60" />
          <span class="default">默认 10</span>
        </div>
        <div class="param">
          <label title="正常到期后进入冷却的交易日数">到期冷却天数</label>
          <input type="number" v-model.number="config.strategy6.expired_cooldown_days" @input="markDirty" min="1" max="30" />
          <span class="default">默认 5</span>
        </div>
        <div class="param">
          <label title="形态失效后进入冷却的交易日数">失败冷却天数</label>
          <input type="number" v-model.number="config.strategy6.failed_cooldown_days" @input="markDirty" min="1" max="60" />
          <span class="default">默认 10</span>
        </div>
        <div class="param">
          <label title="尾部5日收盘波动上限">尾部收盘波动</label>
          <input type="number" v-model.number="config.strategy6.tail_close_range_5" @input="markDirty" min="0" max="1" step="0.01" />
          <span class="default">默认 0.08</span>
        </div>
        <div class="param">
          <label title="尾部量干门槛，V5/V20 不高于该值">尾部 V5/V20</label>
          <input type="number" v-model.number="config.strategy6.tail_volume_ratio_5_20" @input="markDirty" min="0" max="2" step="0.01" />
          <span class="default">默认 0.75</span>
        </div>
        <div class="param">
          <label title="强量干门槛，用于就绪候选">强量干 V5/V20</label>
          <input type="number" v-model.number="config.strategy6.tail_strong_volume_ratio_5_20" @input="markDirty" min="0" max="2" step="0.01" />
          <span class="default">默认 0.60</span>
        </div>
        <div class="param">
          <label title="放量下跌一票否决的跌幅">放量下跌跌幅</label>
          <input type="number" v-model.number="config.strategy6.big_down_return" @input="markDirty" min="-1" max="0" step="0.01" />
          <span class="default">默认 -0.07</span>
        </div>
        <div class="param">
          <label title="观察候选最低 RR2">观察最低 RR2</label>
          <input type="number" v-model.number="config.strategy6.rr2_min_watch" @input="markDirty" min="0" max="20" step="0.1" />
          <span class="default">默认 1.5</span>
        </div>
        <div class="param">
          <label title="重点候选最低 RR2">重点最低 RR2</label>
          <input type="number" v-model.number="config.strategy6.rr2_min_key" @input="markDirty" min="0" max="20" step="0.1" />
          <span class="default">默认 2.0</span>
        </div>
        <div class="param">
          <label title="就绪候选最低 RR2">就绪最低 RR2</label>
          <input type="number" v-model.number="config.strategy6.rr2_min_ready" @input="markDirty" min="0" max="20" step="0.1" />
          <span class="default">默认 2.5</span>
        </div>
        <div class="param">
          <label title="就绪候选最低总分">就绪最低分</label>
          <input type="number" v-model.number="config.strategy6.ready_min_score" @input="markDirty" min="0" max="100" step="1" />
          <span class="default">默认 85</span>
        </div>
        <div class="param">
          <label title="重点候选最低总分">重点最低分</label>
          <input type="number" v-model.number="config.strategy6.key_min_score" @input="markDirty" min="0" max="100" step="1" />
          <span class="default">默认 75</span>
        </div>
        <div class="param">
          <label title="观察候选最低总分">观察最低分</label>
          <input type="number" v-model.number="config.strategy6.watch_min_score" @input="markDirty" min="0" max="100" step="1" />
          <span class="default">默认 60</span>
        </div>
      </div>

      <h4 class="subsection-title">TTM Squeeze 质量排序</h4>
      <div class="toggle-row">
        <div class="toggle-item">
          <span>启用TTM质量加分</span>
          <button data-test="strategy6-ttm-enabled" class="toggle" :class="{ active: config.strategy6.ttm_squeeze.enabled }"
            @click="toggleStrategy6Ttm('enabled')">{{ config.strategy6.ttm_squeeze.enabled ? '开' : '关' }}</button>
        </div>
      </div>
      <div class="param-grid">
        <div class="param"><label title="布林带计算周期">布林带周期</label><input data-test="strategy6-ttm-bb-period" type="number" v-model.number="config.strategy6.ttm_squeeze.bb_period" @input="markDirty" min="5" max="120" /><span class="default">默认 20</span></div>
        <div class="param"><label title="布林带标准差倍数">布林带倍数</label><input type="number" v-model.number="config.strategy6.ttm_squeeze.bb_stddev" @input="markDirty" min="0.01" max="10" step="0.1" /><span class="default">默认 2.0</span></div>
        <div class="param"><label title="Keltner中轨EMA周期">Keltner EMA周期</label><input type="number" v-model.number="config.strategy6.ttm_squeeze.kc_ema_period" @input="markDirty" min="5" max="120" /><span class="default">默认 20</span></div>
        <div class="param"><label title="Keltner通道ATR周期">Keltner ATR周期</label><input type="number" v-model.number="config.strategy6.ttm_squeeze.kc_atr_period" @input="markDirty" min="5" max="120" /><span class="default">默认 20</span></div>
        <div class="param"><label title="Keltner通道ATR倍数">Keltner ATR倍数</label><input data-test="strategy6-ttm-kc-multiplier" type="number" v-model.number="config.strategy6.ttm_squeeze.kc_atr_multiplier" @input="markDirty" min="0.01" max="10" step="0.1" /><span class="default">默认 1.5</span></div>
        <div class="param"><label title="TTM线性回归动量周期">动量周期</label><input data-test="strategy6-ttm-momentum-period" type="number" v-model.number="config.strategy6.ttm_squeeze.momentum_period" @input="markDirty" min="5" max="120" /><span class="default">默认 20</span></div>
        <div class="param"><label title="多头挤压加3分所需的最少连续交易日">多头挤压最少天数</label><input type="number" v-model.number="config.strategy6.ttm_squeeze.bullish_squeeze_min_days" @input="markDirty" min="1" max="20" /><span class="default">默认 3</span></div>
        <div class="param"><label title="本版本固定为4，避免改变候选资格">最大排序加分</label><input type="number" v-model.number="config.strategy6.ttm_squeeze.max_ranking_bonus" @input="markDirty" min="4" max="4" /><span class="default">固定 4</span></div>
      </div>
      <p class="section-note">ⓘ TTM只增加独立质量分和同类候选排序，不改变策略6原100分、硬过滤、候选类型和交易计划。</p>

      <h4 class="subsection-title">稳定箱体尾部路径</h4>
      <div class="toggle-row">
        <div class="toggle-item">
          <span>启用稳定箱体路径</span>
          <button data-test="strategy6-box-tail-enabled" class="toggle" :class="{ active: config.strategy6.box_tail.enabled }"
            @click="toggleStrategy6BoxTail('enabled')">{{ config.strategy6.box_tail.enabled ? '开' : '关' }}</button>
        </div>
        <div class="toggle-item">
          <span>K线紧密排列确认</span>
          <button data-test="strategy6-compact-enabled" class="toggle" :class="{ active: config.strategy6.box_tail.compact_kline.enabled }"
            @click="toggleStrategy6CompactKline('enabled')">{{ config.strategy6.box_tail.compact_kline.enabled ? '开' : '关' }}</button>
        </div>
      </div>
      <div class="param-grid">
        <div class="param"><label>箱体最短天数</label><input data-test="strategy6-box-min-days" type="number" v-model.number="config.strategy6.box_tail.min_box_days" @input="markDirty" min="5" max="30" /><span class="default">默认 5</span></div>
        <div class="param"><label>箱体最长天数</label><input data-test="strategy6-box-max-days" type="number" v-model.number="config.strategy6.box_tail.max_box_days" @input="markDirty" min="5" max="30" /><span class="default">默认 30</span></div>
        <div class="param"><label>优质箱体宽度</label><input type="number" v-model.number="config.strategy6.box_tail.premium_box_width_max" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.12</span></div>
        <div class="param"><label>普通箱体宽度</label><input data-test="strategy6-box-width-normal" type="number" v-model.number="config.strategy6.box_tail.normal_box_width_max" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.18</span></div>
        <div class="param"><label>下沿测试向上容差</label><input type="number" v-model.number="config.strategy6.box_tail.low_test_tolerance_up" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.02</span></div>
        <div class="param"><label>测试收盘向下容差</label><input type="number" v-model.number="config.strategy6.box_tail.low_test_close_tolerance_down" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.02</span></div>
        <div class="param"><label>有效跌破容差</label><input type="number" v-model.number="config.strategy6.box_tail.broken_close_tolerance" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.03</span></div>
        <div class="param"><label>最少下沿测试</label><input type="number" v-model.number="config.strategy6.box_tail.min_box_low_test_count" @input="markDirty" min="1" max="10" /><span class="default">默认 2</span></div>
        <div class="param"><label>最低中枢变化</label><input type="number" v-model.number="config.strategy6.box_tail.min_center_shift" @input="markDirty" min="-1" max="1" step="0.01" /><span class="default">默认 -0.03</span></div>
        <div class="param"><label>优质中枢变化</label><input type="number" v-model.number="config.strategy6.box_tail.premium_center_shift" @input="markDirty" min="-1" max="1" step="0.01" /><span class="default">默认 0</span></div>
        <div class="param"><label>最大箱体量缩比</label><input type="number" v-model.number="config.strategy6.box_tail.max_volume_contraction_ratio" @input="markDirty" min="0" max="2" step="0.01" /><span class="default">默认 0.85</span></div>
        <div class="param"><label>优质箱体量缩比</label><input type="number" v-model.number="config.strategy6.box_tail.premium_volume_contraction_ratio" @input="markDirty" min="0" max="2" step="0.01" /><span class="default">默认 0.70</span></div>
        <div class="param"><label>当前收盘下沿容差</label><input type="number" v-model.number="config.strategy6.box_tail.current_close_low_tolerance" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.03</span></div>
        <div class="param"><label>当前收盘上沿容差</label><input type="number" v-model.number="config.strategy6.box_tail.current_close_high_tolerance" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.03</span></div>
        <div class="param"><label>箱体尾部最大量比</label><input type="number" v-model.number="config.strategy6.box_tail.tail_volume_ratio_max" @input="markDirty" min="0" max="2" step="0.01" /><span class="default">默认 0.75</span></div>
        <div class="param"><label>优质尾部最大量比</label><input type="number" v-model.number="config.strategy6.box_tail.premium_tail_volume_ratio_max" @input="markDirty" min="0" max="2" step="0.01" /><span class="default">默认 0.60</span></div>
        <div class="param"><label>支撑就绪位置</label><input type="number" v-model.number="config.strategy6.box_tail.support_ready_position_max" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.40</span></div>
        <div class="param"><label>突破就绪位置</label><input type="number" v-model.number="config.strategy6.box_tail.breakout_ready_position_min" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.75</span></div>
      </div>

      <h4 class="subsection-title">K线紧密排列参数</h4>
      <div class="param-grid">
        <div class="param"><label>紧密排列窗口</label><input data-test="strategy6-compact-window" type="number" v-model.number="config.strategy6.box_tail.compact_kline.window_days" @input="markDirty" min="3" max="10" /><span class="default">默认 5</span></div>
        <div class="param"><label>平均实体上限</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.avg_body_ratio_max" @input="markDirty" min="0" max="1" step="0.001" /><span class="default">默认 0.025</span></div>
        <div class="param"><label>优质平均实体</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.premium_avg_body_ratio_max" @input="markDirty" min="0" max="1" step="0.001" /><span class="default">默认 0.018</span></div>
        <div class="param"><label>最大实体上限</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.max_body_ratio_max" @input="markDirty" min="0" max="1" step="0.001" /><span class="default">默认 0.04</span></div>
        <div class="param"><label>收盘集中区间</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.close_range_max" @input="markDirty" min="0" max="1" step="0.001" /><span class="default">默认 0.05</span></div>
        <div class="param"><label>优质收盘区间</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.premium_close_range_max" @input="markDirty" min="0" max="1" step="0.001" /><span class="default">默认 0.03</span></div>
        <div class="param"><label>最小K线重叠比</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.min_overlap_ratio" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.50</span></div>
        <div class="param"><label>优质K线重叠比</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.premium_overlap_ratio" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.65</span></div>
        <div class="param"><label>最少重叠组数</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.min_overlap_pair_count" @input="markDirty" min="1" max="9" /><span class="default">默认 3</span></div>
        <div class="param"><label>最大跳空比例</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.max_gap_ratio" @input="markDirty" min="0" max="1" step="0.01" /><span class="default">默认 0.03</span></div>
        <div class="param"><label>ATR收缩比上限</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.atr_contraction_ratio_max" @input="markDirty" min="0" max="2" step="0.01" /><span class="default">默认 0.80</span></div>
        <div class="param"><label>优质ATR收缩比</label><input type="number" v-model.number="config.strategy6.box_tail.compact_kline.premium_atr_contraction_ratio_max" @input="markDirty" min="0" max="2" step="0.01" /><span class="default">默认 0.65</span></div>
      </div>

      <template v-if="config.strategy6.brooks_tail">
        <h4 class="subsection-title">Brooks价格行为第三路径</h4>
        <div class="toggle-row">
          <div class="toggle-item">
            <span>启用Brooks独立路径</span>
            <button data-test="strategy6-brooks-enabled" class="toggle" :class="{ active: config.strategy6.brooks_tail.enabled }"
              @click="toggleStrategy6Brooks(null, 'enabled')">{{ config.strategy6.brooks_tail.enabled ? '开' : '关' }}</button>
          </div>
          <div class="toggle-item">
            <span>B级启动仅观察</span>
            <button class="toggle" :class="{ active: config.strategy6.brooks_tail.context.allow_grade_b_watch_only }"
              @click="toggleStrategy6Brooks('context', 'allow_grade_b_watch_only')">{{ config.strategy6.brooks_tail.context.allow_grade_b_watch_only ? '开' : '关' }}</button>
          </div>
        </div>

        <h4 class="subsection-title">上涨背景</h4>
        <div class="param-grid">
          <div class="param"><label>MA20斜率窗口</label><input data-test="strategy6-brooks-context-window" type="number" v-model.number="config.strategy6.brooks_tail.context.ma20_slope_window_days" @input="markDirty" min="2" max="60" /><span class="default">默认 10</span></div>
          <div class="param"><label>高低点序列窗口</label><input type="number" v-model.number="config.strategy6.brooks_tail.context.lower_high_low_window_days" @input="markDirty" min="5" max="60" /><span class="default">默认 10</span></div>
          <div class="param"><label>最大下移序列数</label><input type="number" v-model.number="config.strategy6.brooks_tail.context.max_lower_high_low_sequence" @input="markDirty" min="0" max="10" /><span class="default">默认 2</span></div>
          <div class="param"><label>跌破MA20 ATR容差</label><input type="number" v-model.number="config.strategy6.brooks_tail.context.close_below_ma20_atr_tolerance" @input="markDirty" min="0" max="3" step="0.1" /><span class="default">默认 0.5</span></div>
        </div>

        <h4 class="subsection-title">卖压衰竭</h4>
        <div class="param-grid">
          <div class="param"><label>卖压观察窗口</label><input data-test="strategy6-brooks-selling-window" type="number" v-model.number="config.strategy6.brooks_tail.selling_pressure.window_days" @input="markDirty" min="3" max="30" /><span class="default">默认 7</span></div>
          <div class="param"><label>最多强空方K线</label><input type="number" v-model.number="config.strategy6.brooks_tail.selling_pressure.max_strong_bear_bar_count" @input="markDirty" min="0" max="30" /><span class="default">默认 1</span></div>
          <div class="param"><label>最多空方跟进</label><input type="number" v-model.number="config.strategy6.brooks_tail.selling_pressure.max_bear_follow_through_count" @input="markDirty" min="0" max="30" /><span class="default">默认 1</span></div>
          <div class="param"><label>最多连续阴线</label><input type="number" v-model.number="config.strategy6.brooks_tail.selling_pressure.max_consecutive_bear_bars" @input="markDirty" min="0" max="30" /><span class="default">默认 2</span></div>
        </div>

        <h4 class="subsection-title">价格稳定与量干</h4>
        <div class="param-grid">
          <div class="param"><label>稳定判断窗口</label><input data-test="strategy6-brooks-stability-window" type="number" v-model.number="config.strategy6.brooks_tail.price_stability.compact_window_days" @input="markDirty" min="3" max="10" /><span class="default">默认 5</span></div>
          <div class="param"><label>收盘区间上限</label><input type="number" v-model.number="config.strategy6.brooks_tail.price_stability.close_range_max" @input="markDirty" min="0" max="2" step="0.01" /><span class="default">默认 0.08</span></div>
          <div class="param"><label>优质收盘区间</label><input type="number" v-model.number="config.strategy6.brooks_tail.price_stability.premium_close_range_max" @input="markDirty" min="0" max="2" step="0.01" /><span class="default">默认 0.05</span></div>
          <div class="param"><label>尾部量比上限</label><input type="number" v-model.number="config.strategy6.brooks_tail.volume_dry.tail_volume_ratio_max" @input="markDirty" min="0.01" max="2" step="0.01" /><span class="default">默认 0.75</span></div>
          <div class="param"><label>优质量干比</label><input data-test="strategy6-brooks-volume-premium" type="number" v-model.number="config.strategy6.brooks_tail.volume_dry.premium_tail_volume_ratio_max" @input="markDirty" min="0.01" max="2" step="0.01" /><span class="default">默认 0.60</span></div>
          <div class="param"><label>量能基准窗口</label><input type="number" v-model.number="config.strategy6.brooks_tail.volume_dry.baseline_window_days" @input="markDirty" min="10" max="60" /><span class="default">默认 20</span></div>
        </div>

        <h4 class="subsection-title">结构识别</h4>
        <div class="toggle-row">
          <div class="toggle-item"><span>二次入场识别</span><button class="toggle" :class="{ active: config.strategy6.brooks_tail.second_entry.enabled }" @click="toggleStrategy6Brooks('second_entry', 'enabled')">{{ config.strategy6.brooks_tail.second_entry.enabled ? '开' : '关' }}</button></div>
          <div class="toggle-item"><span>假跌破识别</span><button class="toggle" :class="{ active: config.strategy6.brooks_tail.failed_breakout.enabled }" @click="toggleStrategy6Brooks('failed_breakout', 'enabled')">{{ config.strategy6.brooks_tail.failed_breakout.enabled ? '开' : '关' }}</button></div>
          <div class="toggle-item"><span>紧密结构分类</span><button class="toggle" :class="{ active: config.strategy6.brooks_tail.compact_structure.enabled }" @click="toggleStrategy6Brooks('compact_structure', 'enabled')">{{ config.strategy6.brooks_tail.compact_structure.enabled ? '开' : '关' }}</button></div>
        </div>
        <div class="param-grid">
          <div class="param"><label>二次低点最短间隔</label><input type="number" v-model.number="config.strategy6.brooks_tail.second_entry.min_separation_days" @input="markDirty" min="1" max="15" /><span class="default">默认 2</span></div>
          <div class="param"><label>二次低点最长间隔</label><input type="number" v-model.number="config.strategy6.brooks_tail.second_entry.max_separation_days" @input="markDirty" min="1" max="30" /><span class="default">默认 15</span></div>
          <div class="param"><label>假跌破收回天数</label><input type="number" v-model.number="config.strategy6.brooks_tail.failed_breakout.recovery_days" @input="markDirty" min="1" max="5" /><span class="default">默认 2</span></div>
          <div class="param"><label>紧密区下界</label><input type="number" v-model.number="config.strategy6.brooks_tail.compact_structure.middle_zone_low" @input="markDirty" min="0" max="1" step="0.05" /><span class="default">默认 0.35</span></div>
          <div class="param"><label>紧密区上界</label><input type="number" v-model.number="config.strategy6.brooks_tail.compact_structure.middle_zone_high" @input="markDirty" min="0" max="1" step="0.05" /><span class="default">默认 0.70</span></div>
          <div class="param"><label>最多方向变化</label><input type="number" v-model.number="config.strategy6.brooks_tail.compact_structure.max_direction_changes" @input="markDirty" min="0" max="10" /><span class="default">默认 3</span></div>
          <div class="param"><label>最多长影线K线</label><input type="number" v-model.number="config.strategy6.brooks_tail.compact_structure.max_long_shadow_bar_count" @input="markDirty" min="0" max="10" /><span class="default">默认 2</span></div>
        </div>

        <h4 class="subsection-title">交易触发</h4>
        <div class="toggle-row">
          <div class="toggle-item"><span>启用跨日触发确认</span><button class="toggle" :class="{ active: config.strategy6.brooks_tail.trade_trigger.enabled }" @click="toggleStrategy6Brooks('trade_trigger', 'enabled')">{{ config.strategy6.brooks_tail.trade_trigger.enabled ? '开' : '关' }}</button></div>
        </div>
        <div class="param-grid">
          <div class="param"><label>触发有效交易日</label><input data-test="strategy6-brooks-trigger-days" type="number" v-model.number="config.strategy6.brooks_tail.trade_trigger.trigger_valid_days" @input="markDirty" min="1" max="10" /><span class="default">默认 3</span></div>
          <div class="param"><label>最大触发距离 ATR</label><input type="number" v-model.number="config.strategy6.brooks_tail.trade_trigger.max_trigger_distance_atr" @input="markDirty" min="0" max="5" step="0.1" /><span class="default">默认 1.5</span></div>
          <div class="param"><label>突破跟进天数</label><input type="number" v-model.number="config.strategy6.brooks_tail.trade_trigger.breakout_follow_through_days" @input="markDirty" min="1" max="5" /><span class="default">默认 2</span></div>
        </div>

        <h4 class="subsection-title">Brooks评分</h4>
        <div class="param-grid">
          <div class="param"><label>背景分</label><input type="number" v-model.number="config.strategy6.brooks_tail.scoring.context_points" @input="markDirty" min="0" max="20" /><span class="default">默认 4</span></div>
          <div class="param"><label>卖压衰竭分</label><input type="number" v-model.number="config.strategy6.brooks_tail.scoring.selling_pressure_points" @input="markDirty" min="0" max="20" /><span class="default">默认 6</span></div>
          <div class="param"><label>价格稳定分</label><input type="number" v-model.number="config.strategy6.brooks_tail.scoring.price_stability_points" @input="markDirty" min="0" max="20" /><span class="default">默认 4</span></div>
          <div class="param"><label>量干分</label><input type="number" v-model.number="config.strategy6.brooks_tail.scoring.volume_dry_points" @input="markDirty" min="0" max="20" /><span class="default">默认 2</span></div>
          <div class="param"><label>结构分</label><input type="number" v-model.number="config.strategy6.brooks_tail.scoring.setup_points" @input="markDirty" min="0" max="20" /><span class="default">默认 4</span></div>
          <div class="param"><label>Brooks通过分</label><input data-test="strategy6-brooks-pass-score" type="number" v-model.number="config.strategy6.brooks_tail.scoring.pass_score_min" @input="markDirty" min="0" max="20" /><span class="default">默认 14</span></div>
          <div class="param"><label>Brooks优质分</label><input data-test="strategy6-brooks-premium-score" type="number" v-model.number="config.strategy6.brooks_tail.scoring.premium_score_min" @input="markDirty" min="0" max="20" /><span class="default">默认 17</span></div>
        </div>
      </template>
      <div v-else class="info-msg">Brooks配置由后端默认配置补全后显示。</div>

      <div class="info-msg strategy6-info">
        ⓘ 策略6保留真实市场过滤，并在结果页展示扫描时使用的指数快照；板块过滤已移除，不再参与降级或扣分。
      </div>
    </section>

    <!-- Actions -->
    <div class="actions-bar">
      <div v-if="saved" class="saved-msg">✓ 配置已保存</div>
      <div v-if="error" class="error-msg">{{ error }}</div>
      <div class="actions-right">
        <button class="btn-reset" @click="resetAll">恢复默认</button>
        <button class="btn-save" :class="{ dirty }" @click="saveConfig" :disabled="saving">
          {{ saving ? '保存中...' : '保存配置' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useApi } from '../composables/useApi.js'

const { getConfig, updateConfig } = useApi()

const defaultStrategy3Config = {
  enabled: true,
  strategy_window_days: 250,
  minimum_required_days: 180,
  pullback_lookback_days: 60,
  support_lookback_days: 20,
  candidate_min_score: 75,
  core_min_score: 85,
  max_risk_ratio: 0.08,
  trade_candidate_min_score: 88,
  trade_max_risk_ratio: 0.04,
  trade_max_pullback_pct: 0.16,
  max_pullback_from_high: 0.25,
  min_pullback_from_high: 0.12,
  max_recent_range_5: 0.12,
  max_recent_surge_3: 0.10,
  min_relative_strength_60: 0.05,
  volume_shrink_ratio: 0.70,
  dry_return_5_floor: 0.02,
  dry_support_min_test_count: 2,
  dry_support_max_test_count: 2,
}

const defaultStrategy4Config = {
  enabled: true,
  hot_topic_top_n: 16,
  watch_hot_topic_top_n: 16,
  min_hot_topic_score: 65,
  min_hot_topic_signal_count: 1,
  core_leaders_per_topic: 1,
  backup_leaders_per_topic: 2,
  max_total_leaders_per_topic: 3,
  min_leader_strength_score: 50,
  core_leader_strength_score: 50,
  first_wave_lookback_short: 10,
  first_wave_lookback_long: 20,
  min_first_wave_return_10d: 0.10,
  min_first_wave_return_20d: 0.15,
  min_strong_day_count_10d: 1,
  pullback_min_pct: 0.05,
  pullback_max_pct: 0.30,
  pullback_min_days: 1,
  pullback_max_days: 40,
  max_risk_ratio: 0.10,
  aggressive_max_risk_ratio: 0.10,
  min_reward_risk_ratio: 1.5,
  core_leader_min_reward_risk_ratio: 1.5,
  topic_index: {
    enabled: true,
    preferred_sources: ['akshare_ths', 'akshare_eastmoney'],
    history_days: 250,
    min_required_rows: 60,
    require_for_buyable_candidate: true,
    allow_unobserved_for_watch: true,
    max_fetch_topics_per_scan: 30,
    source_retry_attempts: 2,
  },
  topic_index_filters: {
    min_trend_score: 8,
    min_breakout_score: 0,
    min_amount_ratio_5_20: 1,
    max_drawdown_from_high_20: 0.12,
    allowed_phases: ['EARLY_ACCELERATION', 'MAIN_TREND', 'PULLBACK_REPAIR'],
  },
  leader_relative_strength: {
    min_rs_10d: 0.05,
    min_rs_20d: 0.08,
  },
  source_modes: {
    live_external_enabled: true,
    historical_kline_derived_enabled: true,
    merge_mode: 'union_with_confidence',
  },
  derived_source: {
    enabled: true,
    topic_top_n: 30,
    max_topics_per_day: 34,
    max_leaders_per_topic: 5,
    min_topic_hot_score: 50,
    min_confirmed_topic_hot_score: 60,
    min_topic_index_rows: 60,
    min_amount_ratio_5_20: 1,
    min_breadth_ratio: 0.55,
    min_member_count: 5,
    allow_current_members_proxy: true,
    current_members_proxy_trust_level: 'experimental',
  },
  merge_policy: {
    buyable_requires_observed_source: true,
    block_buyable_on_derived_weak_noise: true,
    block_buyable_on_derived_high_risk_climax: true,
    allow_derived_only_watch: true,
    allow_derived_only_buyable: true,
  },
  tracking: {
    enabled: true,
    max_calendar_days: 20,
    strong_attention_days: 20,
    golden_second_wave_days: 20,
    allow_extension_days: 20,
    expire_without_leader_days: 30,
    extension_min_reward_risk_ratio: 2,
    extension_max_risk_ratio: 0.12,
    max_topic_drawdown_since_detected: 0.20,
    max_leader_drawdown_from_first_wave_high: 0.45,
    min_extension_leader_rs_20d: -0.05,
  },
}

const defaultStrategy5Config = {
  enabled: true,
  kline_days: 1100,
  minimum_trading_days: 500,
  min_avg_amount_60d_yi: 15,
  min_avg_amount_30d_yi: 8,
  min_avg_amount_10d_yi: 5,
  kcb_min_avg_amount_60d_yi: 50,
  kcb_min_avg_amount_30d_yi: 30,
  kcb_min_avg_amount_10d_yi: 20,
  strength_ret_20d: 0.20,
  strength_ret_10d: 0.12,
  strength_ret_5d: 0.08,
  strength_ret_50d: 0.35,
  strength_ret_50d_min_20d: 0.05,
  strength_ret_50d_ma20_ratio: 0.98,
  strength_ret_50d_max_amp_10d: 0.30,
  strength_ret_50d_max_decline_5d: -0.06,
  single_day_surge_return: 0.07,
  single_day_surge_volume_ratio: 1.8,
  near_120d_high_ratio: 0.98,
  max_amp_5d: 0.22,
  max_amp_10d: 0.45,
  max_drawdown_20d: -0.30,
  max_decline_5d: -0.08,
  volume_down_return: -0.07,
  volume_down_ratio: 1.5,
  ma50_min_ratio: 0.92,
  key_candidate_min_support_score: 8,
  volume_dry_min_score_key: 14,
  volume_dry_min_score_watch: 10,
  trade_candidate_min_score: 68,
  trade_volume_dry_min_score: 13,
  trade_short_weighted_min_score: 76,
  trade_total_score_weight: 0.75,
  trade_short_strength_weight: 1.25,
  trade_allow_ret50: false,
  trade_allow_ma5_support: false,
  volume_dry_ratio_5_20: 0.75,
  volume_dry_strong_ratio_5_20: 0.65,
  volume_dry_extreme_ratio_5_20: 0.50,
  volume_dry_ratio_5_50: 0.70,
  volume_dry_percentile_60: 0.25,
  volume_dry_down_volume_ratio_5: 0.60,
  volume_dry_down_day_avg_ratio_20: 0.90,
  volume_dry_big_down_return: -0.05,
  volume_dry_big_down_volume_ratio: 1.30,
  volume_dry_consecutive_bear_days: 2,
  volume_dry_close_range_5: 0.06,
  volume_dry_atr_contract_ratio: 0.85,
  volume_dry_direction_efficiency: 0.35,
}

const defaultStrategy6BoxTailConfig = {
  enabled: true,
  min_box_days: 5,
  max_box_days: 30,
  premium_box_width_max: 0.12,
  normal_box_width_max: 0.18,
  low_test_tolerance_up: 0.02,
  low_test_close_tolerance_down: 0.02,
  broken_close_tolerance: 0.03,
  min_box_low_test_count: 2,
  min_center_shift: -0.03,
  premium_center_shift: 0.0,
  max_volume_contraction_ratio: 0.85,
  premium_volume_contraction_ratio: 0.70,
  current_close_low_tolerance: 0.03,
  current_close_high_tolerance: 0.03,
  tail_volume_ratio_max: 0.75,
  premium_tail_volume_ratio_max: 0.60,
  support_ready_position_max: 0.40,
  breakout_ready_position_min: 0.75,
  compact_kline: {
    enabled: true,
    window_days: 5,
    avg_body_ratio_max: 0.025,
    premium_avg_body_ratio_max: 0.018,
    max_body_ratio_max: 0.04,
    close_range_max: 0.05,
    premium_close_range_max: 0.03,
    min_overlap_ratio: 0.50,
    premium_overlap_ratio: 0.65,
    min_overlap_pair_count: 3,
    max_gap_ratio: 0.03,
    atr_contraction_ratio_max: 0.80,
    premium_atr_contraction_ratio_max: 0.65,
  },
}

const defaultStrategy6TtmSqueezeConfig = {
  enabled: true,
  bb_period: 20,
  bb_stddev: 2.0,
  kc_ema_period: 20,
  kc_atr_period: 20,
  kc_atr_multiplier: 1.5,
  momentum_period: 20,
  bullish_squeeze_min_days: 3,
  max_ranking_bonus: 4,
}

const defaultStrategy6Config = {
  enabled: true,
  decision_profile: 'formal_original',
  kline_days: 1100,
  minimum_trading_days: 500,
  min_avg_amount_60d_yi: 3,
  min_avg_amount_30d_yi: 5,
  min_avg_amount_10d_yi: 5,
  amount10_vs_30_min_ratio: 0.8,
  enable_market_filter: true,
  market_filter_mode: 'downgrade',
  start_lookback_days: 60,
  start_age_min_days: 5,
  start_age_max_days: 60,
  consolidation_min_days: 5,
  consolidation_max_days: 40,
  tail_window_days: 5,
  pattern_filter_enabled: true,
  pattern_filter_mode: 'score_only',
  pattern_pivot_proximity_pct: 0.05,
  breakout_extended_max_pct: 0.08,
  vcp_contraction_range_ratio: 0.90,
  vcp_contraction_volume_ratio: 0.90,
  vcp_min_first_range: 0.08,
  vcp_first_contraction_max_range: 0.32,
  vcp_rebound_min_pct: 0.03,
  vcp_rebound_confirm_days: 2,
  vcp_low_warning_ratio: 0.99,
  vcp_history_max_start_loss_pct: 0.15,
  vcp_history_max_drawdown_pct: 0.20,
  vcp_history_bearish_trend_days: 5,
  cup_depth_min: 0.12,
  cup_depth_max: 0.35,
  platform_max_range: 0.12,
  support_cluster_price_pct: 0.015,
  support_cluster_atr_multiplier: 0.50,
  support_zone_price_pct: 0.01,
  support_zone_atr_multiplier: 0.30,
  support_test_lookback: 10,
  normal_start_return: 0.07,
  normal_start_volume_ratio: 2.0,
  normal_start_close_position: 0.65,
  normal_start_min_amount_yi: 2,
  normal_start_self_amount_percentile: 0.90,
  limit_up_volume_ratio: 1.5,
  low_volume_limit_up_min_ratio: 0.6,
  near_120d_high_ratio: 0.98,
  min_relative_strength_20: 0.10,
  max_amp_5d_s: 0.25,
  max_amp_10d_s: 0.45,
  max_pullback_20d_s: -0.30,
  max_amp_5d_a: 0.22,
  max_amp_10d_a: 0.40,
  max_pullback_20d_a: -0.26,
  max_amp_5d_b: 0.18,
  max_amp_10d_b: 0.35,
  max_pullback_20d_b: -0.22,
  absolute_max_amp_10d: 0.50,
  absolute_max_pullback_20d: -0.35,
  ma50_min_ratio: 0.92,
  tail_close_range_5: 0.08,
  tail_volume_ratio_5_20: 0.75,
  tail_strong_volume_ratio_5_20: 0.60,
  tail_min_return_5: -0.06,
  tail_min_return_3: -0.04,
  big_down_return: -0.07,
  big_down_volume_ratio: 1.5,
  rr2_min_watch: 1.5,
  rr2_min_key: 2.0,
  rr2_min_ready: 2.5,
  target_2_cap_pct: 0.35,
  stop_key_support_pct: 0.03,
  stop_atr_multiplier: 0.8,
  buy_zone_valid_days: 3,
  max_watch_days: 10,
  expired_cooldown_days: 5,
  failed_cooldown_days: 10,
  ready_min_score: 85,
  key_min_score: 75,
  watch_min_score: 60,
  ttm_squeeze: defaultStrategy6TtmSqueezeConfig,
  box_tail: defaultStrategy6BoxTailConfig,
  brooks_tail: null,
}

const config = reactive({
  market: {},
  liquidity: {},
  data: {
    acquisition_mode: 'legacy_multi_source',
    tickflow_access_mode: 'free',
    tickflow_api_key: '',
    tickflow_api_key_configured: false,
    scan_window_days: 250,
    backtest_window_days: 250,
    daily_sources: ['tencent', 'sina', 'baidu'],
  },
  cup: {},
  handle: {},
  breakout: {},
  decision: {},
  volume_dry: { bad_shrink_max_score: 7, low_position_max_score: 7, volume_stall_max_score: 7, big_bear_max_score: 6 },
  price_stable: { close_tightness_strong_pct: 3, support_break_max_score: 5 },
  risk_reward: { atr_stop_multiplier: 1.2 },
  scheduler: {
    enabled: false,
    serial_dual_scan: {
      enabled: true,
      cron: '15 15 * * 1-5',
      strategy1_failed_retry_rounds: 3,
    },
  },
  strategy2: {
    enabled: true, strategy_window_days: 120, minimum_required_days: 60,
    candidate_min_score: 70, minimum_volume_dry_score: 40, short_term_time_exit_days: 5,
    max_risk_ratio: 0.05, support_lookback_days: 10,
    buy_zone_max_premium: 0.03, stop_loss_buffer: 0.03,
  },
  strategy3: { ...defaultStrategy3Config },
  strategy4: { ...defaultStrategy4Config },
  strategy5: { ...defaultStrategy5Config },
  strategy6: sanitizeStrategy6Config({}),
})

const dirty = ref(false)
const saved = ref(false)
const saving = ref(false)
const error = ref('')
const showAdvanced = ref(false)
const showTickFlowApiKey = ref(false)

// Computed: convert cup depth from 0-1 to percentage for slider display
const cupMinDepth = computed({
  get: () => Math.round((config.cup.min_depth || 0.12) * 100),
  set: (v) => { config.cup.min_depth = v / 100 },
})
const cupMaxDepth = computed({
  get: () => Math.round((config.cup.max_depth || 0.45) * 100),
  set: (v) => { config.cup.max_depth = v / 100 },
})
const cupRoundness = computed({
  get: () => Math.round((config.cup.min_bottom_roundness || 0.15) * 100),
  set: (v) => { config.cup.min_bottom_roundness = v / 100 },
})
const cupLipDeviation = computed({
  get: () => Math.round((config.cup.max_lip_deviation || 0.12) * 100),
  set: (v) => { config.cup.max_lip_deviation = v / 100 },
})
const handleMinDur = computed({
  get: () => config.handle?.min_duration || 5,
  set: (v) => { config.handle.min_duration = v },
})
const handleMaxDur = computed({
  get: () => config.handle?.max_duration || 30,
  set: (v) => { config.handle.max_duration = v },
})
const handleMaxDepth = computed({
  get: () => Math.round((config.handle?.max_depth || 0.18) * 100),
  set: (v) => { config.handle.max_depth = v / 100 },
})
const breakoutBuffer = computed({
  get: () => Math.round((config.breakout?.buffer_pct || 0.02) * 100),
  set: (v) => { config.breakout.buffer_pct = v / 100 },
})
const maxRiskPercent = computed({
  get: () => config.decision?.max_risk_percent ?? 8,
  set: (v) => { config.decision.max_risk_percent = v },
})

// Strategy2 computed: percentage sliders
const maxRiskRatioPct = computed({
  get: () => Math.round((config.strategy2?.max_risk_ratio ?? 0.05) * 100),
  set: (v) => { config.strategy2.max_risk_ratio = v / 100 },
})
const buyZonePremiumPct = computed({
  get: () => Math.round((config.strategy2?.buy_zone_max_premium ?? 0.03) * 100),
  set: (v) => { config.strategy2.buy_zone_max_premium = v / 100 },
})
const stopLossBufferPct = computed({
  get: () => Math.round((config.strategy2?.stop_loss_buffer ?? 0.03) * 100),
  set: (v) => { config.strategy2.stop_loss_buffer = v / 100 },
})

// Strategy3 computed: percentage sliders
const strategy3MaxRiskPct = computed({
  get: () => Number(((config.strategy3?.max_risk_ratio ?? 0.08) * 100).toFixed(1)),
  set: (v) => { ensureStrategy3Config(); config.strategy3.max_risk_ratio = v / 100 },
})
const strategy3TradeMaxRiskPct = computed({
  get: () => Number(((config.strategy3?.trade_max_risk_ratio ?? 0.04) * 100).toFixed(1)),
  set: (v) => { ensureStrategy3Config(); config.strategy3.trade_max_risk_ratio = v / 100 },
})
const strategy3TradeMaxPullbackPct = computed({
  get: () => Number(((config.strategy3?.trade_max_pullback_pct ?? 0.16) * 100).toFixed(1)),
  set: (v) => { ensureStrategy3Config(); config.strategy3.trade_max_pullback_pct = v / 100 },
})
const strategy3MinPullbackPct = computed({
  get: () => Number(((config.strategy3?.min_pullback_from_high ?? 0.12) * 100).toFixed(1)),
  set: (v) => { ensureStrategy3Config(); config.strategy3.min_pullback_from_high = v / 100 },
})
const strategy3MaxPullbackPct = computed({
  get: () => Number(((config.strategy3?.max_pullback_from_high ?? 0.25) * 100).toFixed(1)),
  set: (v) => { ensureStrategy3Config(); config.strategy3.max_pullback_from_high = v / 100 },
})
const strategy3MaxRange5Pct = computed({
  get: () => Number(((config.strategy3?.max_recent_range_5 ?? 0.12) * 100).toFixed(1)),
  set: (v) => { ensureStrategy3Config(); config.strategy3.max_recent_range_5 = v / 100 },
})
const strategy3MaxSurge3Pct = computed({
  get: () => Number(((config.strategy3?.max_recent_surge_3 ?? 0.10) * 100).toFixed(1)),
  set: (v) => { ensureStrategy3Config(); config.strategy3.max_recent_surge_3 = v / 100 },
})
const strategy3MinRSPct = computed({
  get: () => Number(((config.strategy3?.min_relative_strength_60 ?? 0.05) * 100).toFixed(1)),
  set: (v) => { ensureStrategy3Config(); config.strategy3.min_relative_strength_60 = v / 100 },
})

const strategy4PullbackMinPct = computed({
  get: () => Number(((config.strategy4?.pullback_min_pct ?? 0.08) * 100).toFixed(1)),
  set: (v) => { ensureStrategy4Config(); config.strategy4.pullback_min_pct = v / 100 },
})
const strategy4PullbackMaxPct = computed({
  get: () => Number(((config.strategy4?.pullback_max_pct ?? 0.25) * 100).toFixed(1)),
  set: (v) => { ensureStrategy4Config(); config.strategy4.pullback_max_pct = v / 100 },
})
const strategy4MaxRiskPct = computed({
  get: () => Number(((config.strategy4?.max_risk_ratio ?? 0.15) * 100).toFixed(1)),
  set: (v) => { ensureStrategy4Config(); config.strategy4.max_risk_ratio = v / 100 },
})

const serialDualScanTime = computed({
  get: () => cronToTime(config.scheduler?.serial_dual_scan?.cron ?? '15 15 * * 1-5'),
  set: (v) => {
    ensureSchedulerConfig()
    config.scheduler.serial_dual_scan.cron = timeToWeekdayCron(v)
  },
})

function ensureSchedulerConfig() {
  if (!config.scheduler) {
    config.scheduler = {}
  }
  if (!config.scheduler.serial_dual_scan) {
    config.scheduler.serial_dual_scan = {}
  }
  if (typeof config.scheduler.enabled !== 'boolean') {
    config.scheduler.enabled = false
  }
  if (typeof config.scheduler.serial_dual_scan.enabled !== 'boolean') {
    config.scheduler.serial_dual_scan.enabled = true
  }
  if (!config.scheduler.serial_dual_scan.cron) {
    config.scheduler.serial_dual_scan.cron = '15 15 * * 1-5'
  }
  if (config.scheduler.serial_dual_scan.strategy1_failed_retry_rounds === undefined) {
    config.scheduler.serial_dual_scan.strategy1_failed_retry_rounds = 3
  }
}

function ensureStrategy3Config() {
  config.strategy3 = { ...defaultStrategy3Config, ...(config.strategy3 || {}) }
}

function ensureStrategy4Config() {
  config.strategy4 = mergeStrategy4Config(config.strategy4 || {})
}

function ensureStrategy5Config() {
  config.strategy5 = sanitizeStrategy5Config(config.strategy5 || {})
}

function ensureStrategy6Config() {
  config.strategy6 = sanitizeStrategy6Config(config.strategy6 || {})
}

function sanitizeStrategy5Config(value) {
  const { minimum_kline_days, ...rest } = value || {}
  return { ...defaultStrategy5Config, ...rest }
}

function sanitizeStrategy6Config(value) {
  const known = Object.fromEntries(
    Object.entries(value || {}).filter(([key]) => Object.prototype.hasOwnProperty.call(defaultStrategy6Config, key))
  )
  const boxTail = known.box_tail || {}
  const ttmSqueeze = known.ttm_squeeze || {}
  const brooksTail = known.brooks_tail && typeof known.brooks_tail === 'object'
    ? JSON.parse(JSON.stringify(known.brooks_tail))
    : null
  return {
    ...defaultStrategy6Config,
    ...known,
    ttm_squeeze: {
      ...defaultStrategy6TtmSqueezeConfig,
      ...ttmSqueeze,
    },
    box_tail: {
      ...defaultStrategy6BoxTailConfig,
      ...boxTail,
      compact_kline: {
        ...defaultStrategy6BoxTailConfig.compact_kline,
        ...(boxTail.compact_kline || {}),
      },
    },
    brooks_tail: brooksTail,
  }
}

function mergeStrategy4Config(value) {
  return {
    ...defaultStrategy4Config,
    ...value,
    topic_index: {
      ...defaultStrategy4Config.topic_index,
      ...(value.topic_index || {}),
    },
    topic_index_filters: {
      ...defaultStrategy4Config.topic_index_filters,
      ...(value.topic_index_filters || {}),
    },
    leader_relative_strength: {
      ...defaultStrategy4Config.leader_relative_strength,
      ...(value.leader_relative_strength || {}),
    },
    source_modes: {
      ...defaultStrategy4Config.source_modes,
      ...(value.source_modes || {}),
    },
    derived_source: {
      ...defaultStrategy4Config.derived_source,
      ...(value.derived_source || {}),
    },
    merge_policy: {
      ...defaultStrategy4Config.merge_policy,
      ...(value.merge_policy || {}),
    },
    tracking: {
      ...defaultStrategy4Config.tracking,
      ...(value.tracking || {}),
    },
  }
}

function cronToTime(cron) {
  const parts = String(cron || '').trim().split(/\s+/)
  if (parts.length !== 5) return ''
  const minute = Number(parts[0])
  const hour = Number(parts[1])
  if (!Number.isInteger(minute) || !Number.isInteger(hour)) return ''
  if (minute < 0 || minute > 59 || hour < 0 || hour > 23) return ''
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

function timeToWeekdayCron(time) {
  const match = /^(\d{2}):(\d{2})$/.exec(String(time || ''))
  if (!match) return ''
  const hour = Number(match[1])
  const minute = Number(match[2])
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return ''
  return `${minute} ${hour} * * 1-5`
}

function schedulerTimeIsValid() {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(serialDualScanTime.value)
}

function toggleScheduler(key) {
  ensureSchedulerConfig()
  config.scheduler[key] = !config.scheduler[key]
  if (key === 'enabled') {
    config.scheduler.serial_dual_scan.enabled = config.scheduler.enabled
  }
  markDirty()
}

function toggleSerialDualScan() {
  ensureSchedulerConfig()
  config.scheduler.serial_dual_scan.enabled = !config.scheduler.serial_dual_scan.enabled
  markDirty()
}

function toggleStrategy2(key) {
  config.strategy2[key] = !config.strategy2[key]
  markDirty()
}

function toggleStrategy3(key) {
  ensureStrategy3Config()
  config.strategy3[key] = !config.strategy3[key]
  markDirty()
}

function toggleStrategy4(key) {
  ensureStrategy4Config()
  config.strategy4[key] = !config.strategy4[key]
  markDirty()
}

function toggleStrategy4TopicIndex(key) {
  ensureStrategy4Config()
  config.strategy4.topic_index[key] = !config.strategy4.topic_index[key]
  markDirty()
}

function toggleStrategy5(key) {
  ensureStrategy5Config()
  config.strategy5[key] = !config.strategy5[key]
  markDirty()
}

function toggleStrategy6(key) {
  ensureStrategy6Config()
  config.strategy6[key] = !config.strategy6[key]
  markDirty()
}

function toggleStrategy6BoxTail(key) {
  ensureStrategy6Config()
  config.strategy6.box_tail[key] = !config.strategy6.box_tail[key]
  markDirty()
}

function toggleStrategy6Ttm(key) {
  ensureStrategy6Config()
  config.strategy6.ttm_squeeze[key] = !config.strategy6.ttm_squeeze[key]
  markDirty()
}

function toggleStrategy6CompactKline(key) {
  ensureStrategy6Config()
  config.strategy6.box_tail.compact_kline[key] = !config.strategy6.box_tail.compact_kline[key]
  markDirty()
}

function toggleStrategy6Brooks(section, key) {
  ensureStrategy6Config()
  const brooks = config.strategy6.brooks_tail
  if (!brooks) return
  const target = section ? brooks[section] : brooks
  target[key] = !target[key]
  markDirty()
}

const availableSources = [
  { key: 'tencent', label: '腾讯', tip: '腾讯财经API，实时性好' },
  { key: 'sina', label: 'AkShare-Sina', tip: '通过 AkShare 调用新浪前复权历史行情' },
  { key: 'baidu', label: '百度', tip: '百度股票API备用源' },
]
const availableSourceKeys = new Set(availableSources.map(s => s.key))

const markets = [
  { key: 'include_sh', label: '沪市主板', tip: '上证主板股票，代码 60xxxx' },
  { key: 'include_sz', label: '深市主板', tip: '深证主板股票，代码 00xxxx/002xxx/003xxx' },
  { key: 'include_cyb', label: '创业板', tip: '创业板股票，代码 300xxx/301xxx' },
  { key: 'include_kcb', label: '科创板', tip: '科创板股票，代码 688xxx' },
  { key: 'exclude_bj', label: '排除北交所', tip: '排除北交所股票，代码 8xxxxx/4xxxxx' },
  { key: 'exclude_st', label: '排除 ST/*ST', tip: '排除 ST 及 *ST 股票' },
]

function toggle(section, key) {
  config[section][key] = !config[section][key]
  markDirty()
}

function toggleSource(key) {
  sanitizeDailySources()
  if (!config.data.daily_sources) {
    config.data.daily_sources = availableSources.map(s => s.key)
  }
  const idx = config.data.daily_sources.indexOf(key)
  if (idx >= 0) {
    if (config.data.daily_sources.length <= 1) return  // 至少保留一个
    config.data.daily_sources.splice(idx, 1)
  } else {
    config.data.daily_sources.push(key)
  }
  markDirty()
}

function sanitizeDailySources() {
  if (!config.data) config.data = {}
  if (!['tickflow', 'legacy_multi_source'].includes(config.data.acquisition_mode)) {
    config.data.acquisition_mode = 'legacy_multi_source'
  }
  if (!['free', 'authenticated'].includes(config.data.tickflow_access_mode)) {
    config.data.tickflow_access_mode = 'free'
  }
  const current = Array.isArray(config.data.daily_sources)
    ? config.data.daily_sources
    : availableSources.map(s => s.key)
  const filtered = current.filter(src => availableSourceKeys.has(src))
  config.data.daily_sources = filtered.length ? filtered : availableSources.map(s => s.key)
}

function markDirty() {
  dirty.value = true
  saved.value = false
}

function validate() {
  const errors = []
  sanitizeDailySources()
  const strategy6OnlyFrontend = true
  const strategy6Data = config.data || {}
  if (!strategy6Data.daily_sources || strategy6Data.daily_sources.length === 0) errors.push('至少选择一个日线数据源')
  if (!['tickflow', 'legacy_multi_source'].includes(strategy6Data.acquisition_mode)) errors.push('请选择有效的日线数据获取模式')
  if (!['free', 'authenticated'].includes(strategy6Data.tickflow_access_mode)) errors.push('请选择有效的 TickFlow 访问模式')
  if (!schedulerTimeIsValid()) errors.push('定时任务执行时间格式不正确')

  if (!strategy6OnlyFrontend) {
  const cup = config.cup
  const handle = config.handle

  if (cup.min_duration < 20 || cup.min_duration > 60) errors.push('杯体最短周期需在 20-60 天之间')
  if (cup.max_duration < 100 || cup.max_duration > 250) errors.push('杯体最长周期需在 100-250 天之间')
  if (cup.min_duration >= cup.max_duration) errors.push('杯体最短周期必须小于最长周期')
  if (cup.min_depth < 0.05 || cup.min_depth > 0.20) errors.push('杯体最小深度需在 5%-20% 之间')
  if (cup.max_depth < 0.30 || cup.max_depth > 0.55) errors.push('杯体最大深度需在 30%-55% 之间')
  if (cup.min_depth >= cup.max_depth) errors.push('杯体最小深度必须小于最大深度')
  if (handle.min_duration < 3 || handle.min_duration > 10) errors.push('柄部最短周期需在 3-10 天之间')
  if (handle.max_duration < 20 || handle.max_duration > 40) errors.push('柄部最长周期需在 20-40 天之间')
  if (handle.min_duration >= handle.max_duration) errors.push('柄部最短周期必须小于最长周期')
  if (handle.max_depth < 0.08 || handle.max_depth > 0.25) errors.push('柄部最大回撤需在 8%-25% 之间')

  const liq = config.liquidity
  const dataCfg = config.data || {}
  if (liq.min_avg_turnover < 10000000) errors.push('成交额阈值最低 1000万')
  if (liq.min_stock_price < 1) errors.push('最低股价不能低于 1元')
  if (liq.min_listing_days < 30) errors.push('拉取天数最低 30天')
  if (dataCfg.scan_window_days < 30) errors.push('扫描分析天数最低 30天')
  if (dataCfg.backtest_window_days < 30) errors.push('回测分析天数最低 30天')
  if (dataCfg.scan_window_days > liq.min_listing_days) errors.push('扫描分析天数不能超过日线拉取天数')
  if (!dataCfg.daily_sources || dataCfg.daily_sources.length === 0) errors.push('至少选择一个日线数据源')
  if (!['tickflow', 'legacy_multi_source'].includes(dataCfg.acquisition_mode)) errors.push('请选择有效的日线数据获取模式')
  if (!['free', 'authenticated'].includes(dataCfg.tickflow_access_mode)) errors.push('请选择有效的 TickFlow 访问模式')
  if (!schedulerTimeIsValid()) errors.push('定时任务执行时间格式不正确')

  // Strategy2 validation
  const s2 = config.strategy2 || {}
  if (s2.strategy_window_days < s2.minimum_required_days) errors.push('策略2: 计算天数不能小于最低有效数据天数')
  if (s2.minimum_required_days < 60) errors.push('策略2: 最低有效数据天数 ≥ 60')
  if (s2.strategy_window_days > (liq.min_listing_days || 250)) errors.push('策略2: 计算天数不能超过日线拉取天数')
  if (s2.candidate_min_score < 0 || s2.candidate_min_score > 100) errors.push('策略2: 候选最低分需在 0-100')
  if (s2.minimum_volume_dry_score < 0 || s2.minimum_volume_dry_score > 100) errors.push('策略2: 正式量干最低分需在 0-100')
  if (s2.short_term_time_exit_days < 0 || s2.short_term_time_exit_days > 20) errors.push('策略2: 短线退出建议需在 0-20 天')
  if (s2.max_risk_ratio <= 0 || s2.max_risk_ratio >= 1) errors.push('策略2: 最大风险比需在 (0, 1) 之间')
  if (s2.support_lookback_days < 2) errors.push('策略2: 支撑回看天数 ≥ 2')
  if (s2.buy_zone_max_premium <= 0 || s2.buy_zone_max_premium > 0.2) errors.push('策略2: 买入溢价需在 (0, 20%] 之间')
  if (s2.stop_loss_buffer <= 0 || s2.stop_loss_buffer > 0.2) errors.push('策略2: 止损缓冲需在 (0, 20%] 之间')

  // Strategy3 validation
  ensureStrategy3Config()
  const s3 = config.strategy3 || {}
  if (s3.minimum_required_days < 120) errors.push('策略3: 最低有效数据天数 ≥ 120')
  if (s3.strategy_window_days < s3.minimum_required_days) errors.push('策略3: 计算天数不能小于最低有效数据天数')
  if (s3.strategy_window_days > (liq.min_listing_days || 250)) errors.push('策略3: 计算天数不能超过日线拉取天数')
  if (s3.pullback_lookback_days < 40 || s3.pullback_lookback_days > 120) errors.push('策略3: 回踩回看天数需在 40-120')
  if (s3.support_lookback_days < 10 || s3.support_lookback_days > 40) errors.push('策略3: 支撑回看天数需在 10-40')
  if (s3.candidate_min_score < 0 || s3.candidate_min_score > 100) errors.push('策略3: 候选最低分需在 0-100')
  if (s3.core_min_score < s3.candidate_min_score) errors.push('策略3: 核心候选最低分不能低于候选最低分')
  if (s3.core_min_score < 0 || s3.core_min_score > 100) errors.push('策略3: 核心候选最低分需在 0-100')
  if (s3.max_risk_ratio <= 0 || s3.max_risk_ratio > 0.5) errors.push('策略3: 最大风险比需在 (0, 50%] 之间')
  if (s3.trade_candidate_min_score < s3.candidate_min_score || s3.trade_candidate_min_score > 100) errors.push('策略3: 正式候选分数需 ≥ 候选最低分且 ≤ 100')
  if (s3.trade_max_risk_ratio <= 0 || s3.trade_max_risk_ratio > s3.max_risk_ratio) errors.push('策略3: 正式最大风险需在 (0, 最大风险比] 之间')
  if (s3.min_pullback_from_high < 0 || s3.min_pullback_from_high > 0.5) errors.push('策略3: 最小回踩幅度需在 0-50%')
  if (s3.max_pullback_from_high < s3.min_pullback_from_high || s3.max_pullback_from_high > 0.8) errors.push('策略3: 最大回踩幅度需大于最小回踩且不超过 80%')
  if (s3.trade_max_pullback_pct < s3.min_pullback_from_high || s3.trade_max_pullback_pct > s3.max_pullback_from_high) errors.push('策略3: 正式最大回撤需在最小回踩和最大回踩之间')
  if (s3.max_recent_range_5 <= 0 || s3.max_recent_range_5 > 0.5) errors.push('策略3: 最大5日振幅需在 (0, 50%] 之间')
  if (s3.max_recent_surge_3 <= 0 || s3.max_recent_surge_3 > 0.5) errors.push('策略3: 最大3日涨幅需在 (0, 50%] 之间')
  if (s3.min_relative_strength_60 < -0.5 || s3.min_relative_strength_60 > 0.5) errors.push('策略3: 最低60日相对强度需在 -50%-50%')
  if (s3.volume_shrink_ratio <= 0 || s3.volume_shrink_ratio > 2) errors.push('策略3: 缩量比例需在 (0, 2] 之间')

  // Strategy4 validation
  ensureStrategy4Config()
  const s4 = config.strategy4 || {}
  if (s4.hot_topic_top_n < 1) errors.push('策略4: 热点题材 Top N 至少为 1')
  if (s4.watch_hot_topic_top_n < s4.hot_topic_top_n) errors.push('策略4: 观察题材 Top N 不能小于热点题材 Top N')
  if (s4.min_hot_topic_score < 0 || s4.min_hot_topic_score > 100) errors.push('策略4: 热点最低分需在 0-100')
  if (s4.max_total_leaders_per_topic < s4.core_leaders_per_topic + s4.backup_leaders_per_topic) errors.push('策略4: 每题材最多龙头不能小于核心+备选龙头数')
  if (s4.core_leader_strength_score < s4.min_leader_strength_score) errors.push('策略4: 核心龙头强度不能低于龙头最低分')
  if (s4.pullback_max_pct < s4.pullback_min_pct) errors.push('策略4: 最大回踩不能小于最小回踩')
  if (s4.aggressive_max_risk_ratio < s4.max_risk_ratio) errors.push('策略4: 激进最大风险不能小于标准最大风险')
  if (s4.core_leader_min_reward_risk_ratio > s4.min_reward_risk_ratio) errors.push('策略4: 核心龙头最低收益比不能高于普通最低收益比')
  const s4TopicIndex = s4.topic_index || {}
  if (s4TopicIndex.history_days < 60 || s4TopicIndex.history_days > 1000) errors.push('策略4: 板块K线历史需在 60-1000')
  if (s4TopicIndex.min_required_rows < 2 || s4TopicIndex.min_required_rows > 500) errors.push('策略4: 最低板块K线行数需在 2-500')
  if (s4TopicIndex.history_days < s4TopicIndex.min_required_rows) errors.push('策略4: 板块K线历史不能小于最低行数')

  // Strategy5 validation
  ensureStrategy5Config()
  const s5 = config.strategy5 || {}
  if (s5.kline_days < 260 || s5.kline_days > 3000) errors.push('策略5: K线拉取天数需在 260-3000')
  if (s5.minimum_trading_days < 260 || s5.minimum_trading_days > s5.kline_days) errors.push('策略5: 最低交易天数需在 260 到 K线拉取天数之间')
  if (s5.min_avg_amount_60d_yi < 0 || s5.min_avg_amount_60d_yi > 1000) errors.push('策略5: 主创60日均额需在 0-1000 亿')
  if (s5.min_avg_amount_30d_yi < 0 || s5.min_avg_amount_30d_yi > 1000) errors.push('策略5: 主创30日均额需在 0-1000 亿')
  if (s5.min_avg_amount_10d_yi < 0 || s5.min_avg_amount_10d_yi > 1000) errors.push('策略5: 主创10日均额需在 0-1000 亿')
  if (s5.kcb_min_avg_amount_60d_yi < 0 || s5.kcb_min_avg_amount_60d_yi > 1000) errors.push('策略5: 科创60日均额需在 0-1000 亿')
  if (s5.kcb_min_avg_amount_30d_yi < 0 || s5.kcb_min_avg_amount_30d_yi > 1000) errors.push('策略5: 科创30日均额需在 0-1000 亿')
  if (s5.kcb_min_avg_amount_10d_yi < 0 || s5.kcb_min_avg_amount_10d_yi > 1000) errors.push('策略5: 科创10日均额需在 0-1000 亿')
  if (s5.strength_ret_50d < -1 || s5.strength_ret_50d > 5) errors.push('策略5: 50日补漏强度需在 -1 到 5')
  if (s5.strength_ret_50d_min_20d < -1 || s5.strength_ret_50d_min_20d > 5) errors.push('策略5: 补漏20日最低涨幅需在 -1 到 5')
  if (s5.strength_ret_50d_ma20_ratio < 0 || s5.strength_ret_50d_ma20_ratio > 2) errors.push('策略5: 补漏MA20系数需在 0-2')
  if (s5.strength_ret_50d_max_amp_10d <= 0 || s5.strength_ret_50d_max_amp_10d > 3) errors.push('策略5: 补漏最大10日振幅需在 (0, 3]')
  if (s5.strength_ret_50d_max_decline_5d < -1 || s5.strength_ret_50d_max_decline_5d > 0) errors.push('策略5: 补漏最大5日单跌需在 -1 到 0')
  if (s5.near_120d_high_ratio < 0 || s5.near_120d_high_ratio > 1) errors.push('策略5: 接近120日高比例需在 0-1')
  if (s5.max_amp_5d <= 0 || s5.max_amp_5d > 2) errors.push('策略5: 最大5日振幅需在 (0, 2]')
  if (s5.max_amp_10d <= 0 || s5.max_amp_10d > 3) errors.push('策略5: 最大10日振幅需在 (0, 3]')
  if (s5.max_drawdown_20d < -1 || s5.max_drawdown_20d > 0) errors.push('策略5: 20日最大回撤阈值需在 -1 到 0')
  if (s5.key_candidate_min_support_score < 0 || s5.key_candidate_min_support_score > 10) errors.push('策略5: 重点候选支撑分需在 0-10')
  if (s5.volume_dry_min_score_key < 0 || s5.volume_dry_min_score_key > 20) errors.push('策略5: 重点候选量干分需在 0-20')
  if (s5.volume_dry_min_score_watch < 0 || s5.volume_dry_min_score_watch > s5.volume_dry_min_score_key) errors.push('策略5: 观察候选量干分需在 0 到重点候选量干分之间')
  if (s5.trade_candidate_min_score < 0 || s5.trade_candidate_min_score > 100) errors.push('策略5: 正式候选最低分需在 0-100')
  if (s5.trade_volume_dry_min_score < 0 || s5.trade_volume_dry_min_score > 20) errors.push('策略5: 正式候选量干分需在 0-20')
  if (s5.trade_short_weighted_min_score < 0 || s5.trade_short_weighted_min_score > 150) errors.push('策略5: 短线加权最低分需在 0-150')
  if (s5.trade_total_score_weight < 0 || s5.trade_total_score_weight > 2) errors.push('策略5: 总分权重需在 0-2')
  if (s5.trade_short_strength_weight < 0 || s5.trade_short_strength_weight > 5) errors.push('策略5: 短线强度权重需在 0-5')

  }

  // Strategy6 validation
  ensureStrategy6Config()
  const s6 = config.strategy6 || {}
  if (s6.kline_days < 260 || s6.kline_days > 3000) errors.push('策略6: K线拉取天数需在 260-3000')
  if (s6.minimum_trading_days < 260 || s6.minimum_trading_days > s6.kline_days) errors.push('策略6: 最低交易天数需在 260 到 K线拉取天数之间')
  if (s6.min_avg_amount_60d_yi < 0 || s6.min_avg_amount_60d_yi > 1000) errors.push('策略6: 60日均额需在 0-1000 亿')
  if (s6.min_avg_amount_30d_yi < 0 || s6.min_avg_amount_30d_yi > 1000) errors.push('策略6: 30日均额需在 0-1000 亿')
  if (s6.min_avg_amount_10d_yi < 0 || s6.min_avg_amount_10d_yi > 1000) errors.push('策略6: 10日均额需在 0-1000 亿')
  if (s6.normal_start_return < 0 || s6.normal_start_return > 1) errors.push('策略6: 普通启动涨幅需在 0-1')
  if (s6.normal_start_volume_ratio < 0 || s6.normal_start_volume_ratio > 20) errors.push('策略6: 普通启动量比需在 0-20')
  if (s6.normal_start_min_amount_yi < 0 || s6.normal_start_min_amount_yi > 1000) errors.push('策略6: 普通启动成交额需在 0-1000 亿')
  if (s6.normal_start_self_amount_percentile < 0 || s6.normal_start_self_amount_percentile > 1) errors.push('策略6: 启动成交额自身分位需在 0-1')
  if (s6.near_120d_high_ratio < 0 || s6.near_120d_high_ratio > 1) errors.push('策略6: 接近120日高比例需在 0-1')
  if (!['strict', 'downgrade', 'score_only'].includes(s6.market_filter_mode)) errors.push('策略6: 市场过滤模式必须是严格过滤、降级处理或仅调整评分')
  if (!['strict', 'downgrade', 'score_only'].includes(s6.pattern_filter_mode)) errors.push('策略6: 形态过滤模式必须是严格过滤、降级处理或仅调整评分')
  if (s6.pattern_pivot_proximity_pct <= 0 || s6.pattern_pivot_proximity_pct > 0.20) errors.push('策略6: 形态距突破枢轴最大下偏需在 (0,0.20]')
  if (s6.breakout_extended_max_pct <= 0 || s6.breakout_extended_max_pct > 0.30) errors.push('策略6: 突破过度延伸比例需在 (0,0.30]')
  if (s6.start_age_min_days < 1 || s6.start_age_min_days > s6.start_age_max_days) errors.push('策略6: 最小启动年龄需在 1 到最大启动年龄之间')
  if (s6.start_age_max_days > s6.start_lookback_days) errors.push('策略6: 最大启动年龄不能超过启动回看天数')
  if (s6.consolidation_min_days < 1 || s6.consolidation_min_days > s6.consolidation_max_days) errors.push('策略6: 最小整理天数需不高于最大整理天数')
  if (s6.vcp_contraction_range_ratio <= 0 || s6.vcp_contraction_range_ratio > 1) errors.push('策略6: VCP振幅收缩比需在 (0,1]')
  if (s6.vcp_contraction_volume_ratio <= 0 || s6.vcp_contraction_volume_ratio > 1) errors.push('策略6: VCP量能收缩比需在 (0,1]')
  if (s6.vcp_first_contraction_max_range < s6.vcp_min_first_range || s6.vcp_first_contraction_max_range > 0.50) errors.push('策略6: VCP第一轮最大振幅需不低于最小振幅且不超过0.50')
  if (s6.vcp_rebound_min_pct <= 0 || s6.vcp_rebound_min_pct > 0.20) errors.push('策略6: VCP有效反弹最小涨幅需在 (0,0.20]')
  if (!Number.isInteger(s6.vcp_rebound_confirm_days) || s6.vcp_rebound_confirm_days < 2 || s6.vcp_rebound_confirm_days > 10) errors.push('策略6: VCP反弹确认交易日需为2-10的整数')
  if (s6.vcp_low_warning_ratio < 0.97 || s6.vcp_low_warning_ratio > 1) errors.push('策略6: VCP低点下移提示比例需在 0.97-1')
  if (s6.vcp_history_max_start_loss_pct <= 0 || s6.vcp_history_max_start_loss_pct > 0.50) errors.push('策略6: 历史候选至VCP起点最大跌幅需在 (0,0.50]')
  if (s6.vcp_history_max_drawdown_pct <= 0 || s6.vcp_history_max_drawdown_pct > 0.50) errors.push('策略6: 历史资格最大回撤需在 (0,0.50]')
  if (!Number.isInteger(s6.vcp_history_bearish_trend_days) || s6.vcp_history_bearish_trend_days < 1 || s6.vcp_history_bearish_trend_days > 20) errors.push('策略6: 历史资格空头失效天数需为1-20的整数')
  if (s6.cup_depth_min < 0 || s6.cup_depth_min > s6.cup_depth_max || s6.cup_depth_max > 1) errors.push('策略6: 杯体深度需满足 0 <= 最小值 <= 最大值 <= 1')
  if (s6.support_test_lookback < 5 || s6.support_test_lookback > 40) errors.push('策略6: 支撑测试回看需在 5-40')
  if (s6.min_relative_strength_20 < -1 || s6.min_relative_strength_20 > 1) errors.push('策略6: 最低RS20需在 -1 到 1')
  if (s6.tail_close_range_5 < 0 || s6.tail_close_range_5 > 1) errors.push('策略6: 尾部收盘波动需在 0-1')
  if (s6.tail_volume_ratio_5_20 <= 0 || s6.tail_volume_ratio_5_20 > 2) errors.push('策略6: 尾部 V5/V20 需在 (0,2]')
  if (s6.tail_strong_volume_ratio_5_20 <= 0 || s6.tail_strong_volume_ratio_5_20 > s6.tail_volume_ratio_5_20) errors.push('策略6: 强量干 V5/V20 需大于0且不高于尾部门槛')
  if (s6.big_down_return < -1 || s6.big_down_return > 0) errors.push('策略6: 放量下跌跌幅需在 -1 到 0')
  if (s6.rr2_min_watch < 0 || s6.rr2_min_watch > s6.rr2_min_key) errors.push('策略6: 观察最低 RR2 需不高于重点最低 RR2')
  if (s6.rr2_min_key < s6.rr2_min_watch || s6.rr2_min_key > s6.rr2_min_ready) errors.push('策略6: 重点最低 RR2 需在观察和就绪之间')
  if (s6.rr2_min_ready < s6.rr2_min_key || s6.rr2_min_ready > 20) errors.push('策略6: 就绪最低 RR2 需不低于重点且不超过20')
  if (s6.watch_min_score < 0 || s6.watch_min_score > s6.key_min_score) errors.push('策略6: 观察最低分需在 0 到重点最低分之间')
  if (s6.key_min_score < s6.watch_min_score || s6.key_min_score > s6.ready_min_score) errors.push('策略6: 重点最低分需在观察和就绪之间')
  if (s6.ready_min_score < s6.key_min_score || s6.ready_min_score > 100) errors.push('策略6: 就绪最低分需不低于重点且不超过100')
  if (s6.max_watch_days < 1 || s6.max_watch_days > 60) errors.push('策略6: 最大观察天数需在 1-60')
  const ttm = s6.ttm_squeeze || {}
  const ttmIntegerInRange = (value, min, max) => Number.isInteger(value) && value >= min && value <= max
  const ttmNumberInRange = (value, min, max) => typeof value === 'number' && Number.isFinite(value) && value > min && value <= max
  for (const [key, label] of [['bb_period', '布林带周期'], ['kc_ema_period', 'Keltner EMA周期'], ['kc_atr_period', 'Keltner ATR周期'], ['momentum_period', '动量周期']]) {
    if (!ttmIntegerInRange(ttm[key], 5, 120)) errors.push(`策略6 TTM: ${label}需为5-120的整数`)
  }
  if (!ttmNumberInRange(ttm.bb_stddev, 0, 10)) errors.push('策略6 TTM: 布林带倍数需在 (0,10]')
  if (!ttmNumberInRange(ttm.kc_atr_multiplier, 0, 10)) errors.push('策略6 TTM: Keltner ATR倍数需在 (0,10]')
  if (!ttmIntegerInRange(ttm.bullish_squeeze_min_days, 1, 20)) errors.push('策略6 TTM: 多头挤压最少天数需为1-20的整数')
  if (ttm.max_ranking_bonus !== 4) errors.push('策略6 TTM: 最大排序加分本版本必须为4')
  const box = s6.box_tail || {}
  const compact = box.compact_kline || {}
  if (box.min_box_days < 5 || box.min_box_days > box.max_box_days) errors.push('策略6箱体: 最短天数需在 5 到最长天数之间')
  if (box.max_box_days > 30) errors.push('策略6箱体: 最长天数不能超过 30')
  if (box.premium_box_width_max < 0 || box.premium_box_width_max > box.normal_box_width_max) errors.push('策略6箱体: 优质宽度不能高于普通宽度')
  if (box.normal_box_width_max <= 0 || box.normal_box_width_max > 1) errors.push('策略6箱体: 普通宽度需在 (0,1]')
  if (box.min_box_low_test_count < 1 || box.min_box_low_test_count > 10) errors.push('策略6箱体: 最少下沿测试需在 1-10')
  if (box.premium_volume_contraction_ratio > box.max_volume_contraction_ratio) errors.push('策略6箱体: 优质量缩比不能高于普通量缩比')
  if (box.premium_tail_volume_ratio_max > box.tail_volume_ratio_max) errors.push('策略6箱体: 优质尾部量比不能高于普通量比')
  if (box.support_ready_position_max >= box.breakout_ready_position_min) errors.push('策略6箱体: 支撑位置阈值必须低于突破位置阈值')
  if (compact.window_days < 3 || compact.window_days > 10) errors.push('策略6紧密K线: 窗口需在 3-10')
  if (compact.min_overlap_pair_count < 1 || compact.min_overlap_pair_count >= compact.window_days) errors.push('策略6紧密K线: 最少重叠组数必须小于窗口天数')
  if (compact.premium_avg_body_ratio_max > compact.avg_body_ratio_max) errors.push('策略6紧密K线: 优质平均实体阈值不能高于普通阈值')
  if (compact.premium_close_range_max > compact.close_range_max) errors.push('策略6紧密K线: 优质收盘区间不能高于普通区间')
  if (compact.premium_overlap_ratio < compact.min_overlap_ratio) errors.push('策略6紧密K线: 优质重叠比例不能低于普通比例')
  if (compact.premium_atr_contraction_ratio_max > compact.atr_contraction_ratio_max) errors.push('策略6紧密K线: 优质ATR收缩比不能高于普通比例')

  const brooks = s6.brooks_tail
  if (!brooks || typeof brooks !== 'object') {
    errors.push('策略6 Brooks: 后端未返回完整配置，请刷新页面后重试')
  } else {
    const context = brooks.context || {}
    const selling = brooks.selling_pressure || {}
    const stability = brooks.price_stability || {}
    const volume = brooks.volume_dry || {}
    const second = brooks.second_entry || {}
    const failed = brooks.failed_breakout || {}
    const compactBrooks = brooks.compact_structure || {}
    const trigger = brooks.trade_trigger || {}
    const scoring = brooks.scoring || {}
    const integerInRange = (value, min, max) => Number.isInteger(value) && value >= min && value <= max
    const numberInRange = (value, min, max, lowerExclusive = false) => (
      typeof value === 'number' && Number.isFinite(value)
      && (lowerExclusive ? value > min : value >= min) && value <= max
    )
    if (brooks.mode !== 'independent_path') errors.push('策略6 Brooks: 运行模式必须为独立路径')
    if (!Array.isArray(context.allowed_start_grades) || !context.allowed_start_grades.length || context.allowed_start_grades.some(v => !['S', 'A'].includes(v))) errors.push('策略6 Brooks: 允许启动等级只能包含 S 或 A')
    if (!integerInRange(context.ma20_slope_window_days, 2, 60)) errors.push('策略6 Brooks上涨背景: MA20斜率窗口需在 2-60 的整数')
    if (!integerInRange(context.lower_high_low_window_days, 5, 60)) errors.push('策略6 Brooks上涨背景: 高低点序列窗口需在 5-60 的整数')
    if (!integerInRange(context.max_lower_high_low_sequence, 0, 10)) errors.push('策略6 Brooks上涨背景: 最大下移序列数需在 0-10 的整数')
    if (!numberInRange(context.close_below_ma20_atr_tolerance, 0, 3)) errors.push('策略6 Brooks上涨背景: 跌破MA20 ATR容差需在 0-3')
    if (!integerInRange(selling.window_days, 3, 30)) errors.push('策略6 Brooks卖压: 观察窗口需在 3-30 的整数')
    for (const [value, name] of [[selling.max_strong_bear_bar_count, '强空方K线数'], [selling.max_bear_follow_through_count, '空方跟进数'], [selling.max_consecutive_bear_bars, '连续阴线数']]) {
      if (!integerInRange(value, 0, Number.isInteger(selling.window_days) ? selling.window_days : 30)) errors.push(`策略6 Brooks卖压: 最大${name}不能超过观察窗口且必须为非负整数`)
    }
    if (!integerInRange(stability.compact_window_days, 3, 10)) errors.push('策略6 Brooks价格稳定: 窗口需在 3-10 的整数')
    if (!numberInRange(stability.close_range_max, 0, 2)) errors.push('策略6 Brooks价格稳定: 收盘区间上限需在 0-2')
    if (!numberInRange(stability.premium_close_range_max, 0, 2)) errors.push('策略6 Brooks价格稳定: 优质收盘区间需在 0-2')
    if (stability.premium_close_range_max > stability.close_range_max) errors.push('策略6 Brooks价格稳定: 优质收盘区间不能高于普通区间')
    if (stability.premium_atr_contraction_max > stability.atr_contraction_max) errors.push('策略6 Brooks价格稳定: 优质ATR收缩比不能高于普通比例')
    if (!integerInRange(volume.tail_window_days, 3, 10)) errors.push('策略6 Brooks量干: 尾部窗口需在 3-10 的整数')
    if (!integerInRange(volume.baseline_window_days, 10, 60)) errors.push('策略6 Brooks量干: 基准窗口需在 10-60 的整数')
    if (!numberInRange(volume.tail_volume_ratio_max, 0, 2, true)) errors.push('策略6 Brooks量干: 普通量干比需在 (0,2]')
    if (!numberInRange(volume.premium_tail_volume_ratio_max, 0, 2, true)) errors.push('策略6 Brooks量干: 优质量干比需在 (0,2]')
    else if (volume.premium_tail_volume_ratio_max > volume.tail_volume_ratio_max) errors.push('策略6 Brooks优质量干比不能高于普通量干比')
    if (!integerInRange(second.min_separation_days, 1, 15)) errors.push('策略6 Brooks二次入场: 最短低点间隔需在 1-15 的整数')
    if (!integerInRange(second.max_separation_days, 2, 30)) errors.push('策略6 Brooks二次入场: 最长低点间隔需在 2-30 的整数')
    if (Number.isFinite(second.min_separation_days) && Number.isFinite(second.max_separation_days) && second.min_separation_days > second.max_separation_days) errors.push('策略6 Brooks二次入场: 最短低点间隔不能高于最长间隔')
    if (!integerInRange(failed.recovery_days, 1, 5)) errors.push('策略6 Brooks假跌破: 收回天数需在 1-5 的整数')
    if (!numberInRange(compactBrooks.middle_zone_low, 0, 1)) errors.push('策略6 Brooks紧密结构: 紧密区下界需在 0-1')
    if (!numberInRange(compactBrooks.middle_zone_high, 0, 1)) errors.push('策略6 Brooks紧密结构: 紧密区上界需在 0-1')
    if (Number.isFinite(compactBrooks.middle_zone_low) && Number.isFinite(compactBrooks.middle_zone_high) && compactBrooks.middle_zone_low > compactBrooks.middle_zone_high) errors.push('策略6 Brooks紧密结构: 紧密区下界不能高于上界')
    if (!integerInRange(compactBrooks.max_direction_changes, 0, 10)) errors.push('策略6 Brooks紧密结构: 方向变化次数需在 0-10 的整数')
    if (!integerInRange(compactBrooks.max_long_shadow_bar_count, 0, 10)) errors.push('策略6 Brooks紧密结构: 长影线K线数需在 0-10 的整数')
    if (!integerInRange(trigger.trigger_valid_days, 1, 10)) errors.push('策略6 Brooks交易触发: 有效交易日需在 1-10 的整数')
    if (!numberInRange(trigger.max_trigger_distance_atr, 0, 5)) errors.push('策略6 Brooks交易触发: 最大距离需在 0-5 ATR')
    if (!integerInRange(trigger.breakout_follow_through_days, 1, 5)) errors.push('策略6 Brooks交易触发: 突破跟进天数需在 1-5 的整数')
    const scoreParts = ['context_points', 'selling_pressure_points', 'price_stability_points', 'volume_dry_points', 'setup_points']
    if (scoreParts.some(key => !integerInRange(scoring[key], 0, 20))) errors.push('策略6 Brooks评分: 各分项需在 0-20 的整数')
    if (scoreParts.reduce((sum, key) => sum + Number(scoring[key] || 0), 0) !== 20) errors.push('策略6 Brooks评分: 五项分数合计必须为20')
    if (!integerInRange(scoring.pass_score_min, 0, 20) || !integerInRange(scoring.premium_score_min, 0, 20)) errors.push('策略6 Brooks评分: 通过分和优质分需在 0-20 的整数')
    if (scoring.pass_score_min > scoring.premium_score_min) errors.push('策略6 Brooks通过分不能高于优质分')
  }

  return errors
}

async function saveConfig() {
  const errors = validate()
  if (errors.length) {
    error.value = errors.join('；')
    return
  }
  saving.value = true
  error.value = ''
  try {
    const replacementTickFlowKey = config.data.tickflow_access_mode === 'authenticated'
      ? String(config.data.tickflow_api_key || '').trim()
      : ''
    const dataPayload = {
      ...config.data,
      daily_sources: [...config.data.daily_sources],
    }
    delete dataPayload.tickflow_api_key_configured
    if (replacementTickFlowKey) {
      dataPayload.tickflow_api_key = replacementTickFlowKey
    } else {
      delete dataPayload.tickflow_api_key
    }
    // Only send settings owned by the Strategy6 service UI. The backend
    // deep-merges this payload, preserving legacy strategy configuration.
    const payload = {
      market: { ...config.market },
      data: dataPayload,
      scheduler: {
        enabled: config.scheduler?.enabled === true,
        serial_dual_scan: {
          ...config.scheduler?.serial_dual_scan,
          enabled: config.scheduler?.enabled === true,
        },
      },
      strategy6: sanitizeStrategy6Config(config.strategy6),
    }
    const res = await updateConfig(payload)
    if (res.status === 'ok') {
      if (replacementTickFlowKey) {
        config.data.tickflow_api_key = ''
        config.data.tickflow_api_key_configured = true
        showTickFlowApiKey.value = false
      }
      dirty.value = false
      saved.value = true
      setTimeout(() => { saved.value = false }, 3000)
    } else {
      error.value = res.message || '保存失败'
    }
  } catch (e) {
    error.value = '保存失败，请检查后端服务'
  } finally {
    saving.value = false
  }
}

async function resetAll() {
  try {
    const data = await getConfig()
    if (data.config) {
      Object.assign(config, data.config)
      ensureSchedulerConfig()
      ensureStrategy3Config()
      ensureStrategy4Config()
      ensureStrategy5Config()
      ensureStrategy6Config()
      sanitizeDailySources()
    }
    dirty.value = false
    saved.value = false
    error.value = ''
  } catch (e) {
    error.value = '加载配置失败'
  }
}

onMounted(async () => {
  try {
    const data = await getConfig()
    if (data.config) {
      Object.assign(config, data.config)
      ensureSchedulerConfig()
      ensureStrategy3Config()
      ensureStrategy4Config()
      ensureStrategy5Config()
      ensureStrategy6Config()
      sanitizeDailySources()
    }
  } catch (e) {
    // use defaults
  }
})
</script>

<style scoped>
.page-content { padding: 22px 24px 48px; max-width: 1180px; margin: 0 auto; }
.page-heading { margin-bottom: 16px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
.terminal-kicker { color: var(--gold); font: 10px/1 var(--font-mono); letter-spacing: 0.16em; }
.page-title { margin: 7px 0 3px; font-size: 23px; font-weight: 700; color: var(--text-primary); }
.page-sub { margin: 0; font-size: 12px; color: var(--text-muted); }

.section {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 18px 20px; margin-bottom: 12px;
  box-shadow: var(--shadow-panel);
}
.section-title {
  font-size: 12px; font-weight: 700; letter-spacing: 0.05em; color: var(--text-secondary);
  margin: 0 0 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border);
}

.toggle-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.mode-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; margin-top: 8px; }
.secret-input-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
.secret-input-row input { flex: 1; min-width: 0; }
.key-status { margin-left: 8px; color: var(--text-muted); font-size: 12px; }
.key-status.configured { color: var(--success, #22a06b); }
.mode-option { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); cursor: pointer; background: rgba(16,24,36,0.45); }
.mode-option:hover { border-color: var(--border-light); background: var(--bg-hover); }
.mode-option input { margin-top: 3px; accent-color: var(--accent); }
.mode-option span { display: flex; flex-direction: column; gap: 4px; }
.mode-option small { color: var(--text-muted); line-height: 1.45; }
.toggle-item { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.toggle-label { font-size: 13px; color: var(--text-secondary); min-width: 90px; }
.toggle {
  padding: 4px 14px; border-radius: 4px; border: 1px solid var(--border);
  background: transparent; color: var(--text-muted); font-size: 12px; font-weight: 600; cursor: pointer;
}
.toggle.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.param-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 600px) { .param-grid { grid-template-columns: 1fr; } }
.param label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.param .unit { font-size: 11px; color: var(--text-muted); }
.param .default { font-size: 10px; color: var(--text-muted); margin-top: 2px; display: block; }
.param input[type="range"] { width: 100%; accent-color: var(--accent); }
.param input[type="number"] {
  width: 100%; padding: 6px 10px; border-radius: 4px; border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-primary); font-family: var(--font-mono); font-size: 14px;
}
.range-val { font-family: var(--font-mono); font-size: 18px; font-weight: 700; color: var(--accent); margin-top: 4px; }

.sub-group-title {
  font-size: 12px; color: var(--text-muted); margin: 0 0 10px;
  font-weight: 600;
}

.actions-bar {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 13px 16px; margin-top: 16px;
  position: sticky; bottom: 20px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.35);
}
.saved-msg { color: var(--down-green); font-size: 13px; font-weight: 600; }
.error-msg { color: var(--up-red); font-size: 13px; }
.actions-right { display: flex; gap: 10px; }
.btn-reset {
  padding: 8px 18px; border-radius: 4px; border: 1px solid var(--border);
  background: transparent; color: var(--text-secondary); font-size: 13px; cursor: pointer;
}
.btn-save {
  padding: 8px 24px; border-radius: 4px; border: none;
  background: var(--border); color: var(--text-muted); font-size: 13px; font-weight: 600; cursor: pointer;
}
.btn-save.dirty {
  background: var(--accent); color: #fff;
}
@media (max-width: 720px) {
  .page-content { padding: 16px 12px 38px; }
  .section { padding: 15px 14px; }
  .actions-bar { bottom: 8px; }
}

/* Strategy2 section */
.strategy2-section { border-color: rgba(255, 215, 0, 0.2); }
.strategy2-title { color: #ffd700; }
.strategy4-section { border-color: rgba(249, 115, 22, 0.25); }
.strategy4-title { color: #fb923c; }
.strategy5-section { border-color: rgba(34, 197, 94, 0.25); }
.strategy5-title { color: #86efac; }
.strategy5-info { border-color: rgba(34, 197, 94, 0.25); color: #86efac; }
.section-hint { font-size: 12px; color: var(--text-muted); margin: -10px 0 16px; line-height: 1.5; }
.info-msg {
  margin-top: 16px; padding: 10px 14px; border-radius: 4px;
  background: rgba(255, 215, 0, 0.06); border: 1px solid rgba(255, 215, 0, 0.15);
  font-size: 12px; color: var(--text-muted); line-height: 1.5;
}
</style>
