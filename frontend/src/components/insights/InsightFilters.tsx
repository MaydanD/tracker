import type {
  ConfidenceLevel,
  InsightAreaRead,
  InsightVariableOptionRead,
} from '../../api/insights'

export type PeriodPreset = '30' | '90' | '180' | '365' | 'custom'
/** Presentation filter built from the guardrail verdict the backend returned. */
export type GuardrailChoice = 'admissible' | 'warnings' | 'blocked' | 'all'

export interface FiltersState {
  preset: PeriodPreset
  start: string
  end: string
  confidence: 'all' | ConfidenceLevel
  guardrail: GuardrailChoice
  areaId: 'all' | number
  variableKey: 'all' | string
}

export interface ExplorerState {
  x: string
  y: string
  lag: number
  active: boolean
}

export const PRESET_LABELS: Record<PeriodPreset, string> = {
  '30': '30 дней',
  '90': '90 дней',
  '180': '6 месяцев',
  '365': '1 год',
  custom: 'Свой период',
}

const GROUP_LABELS: Record<string, string> = {
  score: 'Процент выполнения',
  state: 'Состояние дня',
  habit: 'Привычки',
  calendar: 'Календарь',
  other: 'Прочее',
}

const GROUP_ORDER = ['score', 'state', 'habit', 'calendar', 'other']

export const CONFIDENCE_OPTIONS: { value: 'all' | ConfidenceLevel; label: string }[] = [
  { value: 'all', label: 'Все уровни' },
  { value: 'preliminary', label: 'Предварительно' },
  { value: 'stable', label: 'Стабильно' },
  { value: 'well_supported', label: 'Хорошо подтверждено' },
]

export const GUARDRAIL_OPTIONS: { value: GuardrailChoice; label: string }[] = [
  { value: 'admissible', label: 'Прошедшие проверки' },
  { value: 'warnings', label: 'С ограничениями' },
  { value: 'blocked', label: 'Скрытые проверками' },
  { value: 'all', label: 'Все результаты, включая скрытые' },
]

const LAGS = [0, 1, 2, 3, 4, 5, 6, 7]

interface Props {
  state: FiltersState
  explorer: ExplorerState
  variables: InsightVariableOptionRead[]
  areas: InsightAreaRead[]
  onState: (state: FiltersState) => void
  onExplorer: (explorer: ExplorerState) => void
}

/** Period, evidence level, guardrail visibility, area/variable and the explorer. */
export function InsightFilters({ state, explorer, variables, areas, onState, onExplorer }: Props) {
  const inArea = (variable: InsightVariableOptionRead) =>
    state.areaId === 'all' || variable.area_id === state.areaId
  const selectable = variables.filter((variable) => variable.grain === 'daily' && variable.supported)
  const visible = selectable.filter(inArea)
  const grouped = GROUP_ORDER.map((group) => ({
    group,
    items: visible.filter((variable) => variable.group === group),
  })).filter((entry) => entry.items.length > 0)

  const optionLabel = (variable: InsightVariableOptionRead) => variable.label

  return (
    <div className="insight-filters">
      <div className="toolbar">
        <label className="field field--inline">
          <span>Период</span>
          <select
            value={state.preset}
            onChange={(event) => onState({ ...state, preset: event.target.value as PeriodPreset })}
          >
            {(Object.keys(PRESET_LABELS) as PeriodPreset[]).map((preset) => (
              <option key={preset} value={preset}>
                {PRESET_LABELS[preset]}
              </option>
            ))}
          </select>
        </label>

        <label className="field field--inline">
          <span>Начало</span>
          <input
            type="date"
            value={state.start}
            onChange={(event) => onState({ ...state, preset: 'custom', start: event.target.value })}
          />
        </label>

        <label className="field field--inline">
          <span>Конец</span>
          <input
            type="date"
            value={state.end}
            onChange={(event) => onState({ ...state, preset: 'custom', end: event.target.value })}
          />
        </label>

        <label className="field field--inline">
          <span>Уровень подтверждённости</span>
          <select
            value={state.confidence}
            onChange={(event) =>
              onState({ ...state, confidence: event.target.value as FiltersState['confidence'] })
            }
          >
            {CONFIDENCE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field field--inline">
          <span>Статистические проверки</span>
          <select
            value={state.guardrail}
            onChange={(event) =>
              onState({ ...state, guardrail: event.target.value as GuardrailChoice })
            }
          >
            {GUARDRAIL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field field--inline">
          <span>Сфера</span>
          <select
            value={String(state.areaId)}
            onChange={(event) =>
              onState({
                ...state,
                areaId: event.target.value === 'all' ? 'all' : Number(event.target.value),
                variableKey: 'all',
              })
            }
          >
            <option value="all">Все сферы</option>
            {areas.map((area) => (
              <option key={area.id} value={area.id}>
                {area.is_archived ? `${area.name} (в архиве)` : area.name}
              </option>
            ))}
          </select>
        </label>

        <label className="field field--inline">
          <span>Показатель</span>
          <select
            value={state.variableKey}
            onChange={(event) => onState({ ...state, variableKey: event.target.value })}
          >
            <option value="all">Все показатели</option>
            {grouped.map((entry) => (
              <optgroup key={entry.group} label={GROUP_LABELS[entry.group] ?? entry.group}>
                {entry.items.map((variable) => (
                  <option key={variable.key} value={variable.key}>
                    {optionLabel(variable)}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
      </div>

      <fieldset className="insight-explorer">
        <legend>Проверить конкретную связь</legend>
        <div className="toolbar">
          <label className="field field--inline">
            <span>Первый показатель</span>
            <select value={explorer.x} onChange={(event) => onExplorer({ ...explorer, x: event.target.value })}>
              <option value="">Выберите показатель</option>
              {grouped.map((entry) => (
                <optgroup key={`x-${entry.group}`} label={GROUP_LABELS[entry.group] ?? entry.group}>
                  {entry.items.map((variable) => (
                    <option key={`x-${variable.key}`} value={variable.key}>
                      {optionLabel(variable)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          <label className="field field--inline">
            <span>Второй показатель</span>
            <select value={explorer.y} onChange={(event) => onExplorer({ ...explorer, y: event.target.value })}>
              <option value="">Выберите показатель</option>
              {grouped.map((entry) => (
                <optgroup key={`y-${entry.group}`} label={GROUP_LABELS[entry.group] ?? entry.group}>
                  {entry.items.map((variable) => (
                    <option key={`y-${variable.key}`} value={variable.key}>
                      {optionLabel(variable)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          <label className="field field--inline">
            <span>Задержка, дней</span>
            <select value={String(explorer.lag)} onChange={(event) => onExplorer({ ...explorer, lag: Number(event.target.value) })}>
              {LAGS.map((lag) => (
                <option key={lag} value={lag}>
                  {lag === 0 ? 'в те же дни' : `через ${lag}`}
                </option>
              ))}
              {[-1, -2, -3].map((lag) => (
                <option key={lag} value={lag}>
                  {`обратный порядок: ${-lag}`}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            className="button button--primary"
            disabled={explorer.x === '' || explorer.y === '' || explorer.x === explorer.y}
            onClick={() => onExplorer({ ...explorer, active: true })}
          >
            Показать связь
          </button>
          <button
            type="button"
            className="button"
            onClick={() => onExplorer({ ...explorer, active: false })}
          >
            Вернуть обзор
          </button>
        </div>
        <p className="insight-explorer__hint">
          Одна пара проверяется отдельно: сравнение с другими парами здесь не применяется.
        </p>
      </fieldset>
    </div>
  )
}
