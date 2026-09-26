import type { Achievement } from '../../api/records'
import { formatShortDateLabel } from '../../utils/dateUtils'
import { CATEGORY_LABELS, formatCount } from './recordsLabels'

export interface AchievementCardProps {
  achievement: Achievement
}

/**
 * One catalogue milestone.
 *
 * Achieved entries show the real date they were first reached; locked ones show
 * honest progress toward the target. No badges, no confetti — a milestone is
 * either reached or it is not.
 */
export function AchievementCard({ achievement }: AchievementCardProps) {
  const { progress } = achievement
  const ratio =
    progress.target > 0 ? Math.min(1, Math.max(0, progress.current / progress.target)) : 0

  return (
    <li
      className={`achievement achievement--${achievement.achieved ? 'achieved' : 'locked'}`}
      data-category={achievement.category}
      data-achieved={achievement.achieved}
    >
      <div className="achievement__head">
        <span className="achievement__title">{achievement.title}</span>
        <span className="achievement__state">
          {achievement.achieved ? 'Получено' : 'Цель'}
        </span>
      </div>
      <p className="achievement__description">{achievement.description}</p>
      <p className="achievement__category">{CATEGORY_LABELS[achievement.category]}</p>

      {achievement.achieved ? (
        <p className="achievement__date">
          {achievement.achieved_on !== null
            ? `Достигнуто ${formatShortDateLabel(achievement.achieved_on)}`
            : 'Достигнуто'}
        </p>
      ) : (
        <div className="achievement__progress">
          <div
            className="achievement__bar"
            role="progressbar"
            aria-valuenow={progress.current}
            aria-valuemin={0}
            aria-valuemax={progress.target}
            aria-label={`Прогресс: ${achievement.title}`}
          >
            <span className="achievement__fill" style={{ width: `${ratio * 100}%` }} />
          </div>
          <span className="achievement__counts">
            {`${formatCount(progress.current)} / ${formatCount(progress.target)}`}
          </span>
        </div>
      )}
    </li>
  )
}
