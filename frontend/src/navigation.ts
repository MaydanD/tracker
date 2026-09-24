/**
 * Navigation for the Tracker shell.
 *
 * Every entry exists now so the shell is stable; each screen is filled in by the
 * stage noted in `plannedIn` (see PROJECT-SPEC.md section 25).
 */

export interface NavigationItem {
  path: string
  label: string
  summary: string
  plannedIn: string
}

export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    path: '/',
    label: 'Обзор',
    summary: 'Оценка дня, серии выполнений, самочувствие, тепловая карта и комментарии совы.',
    plannedIn: 'Этап 6',
  },
  {
    path: '/check-in',
    label: 'Итоги дня',
    summary: 'Отметки по дням: выполнено, пропущено, осознанный пропуск, количество и заметки.',
    plannedIn: 'Этап 3',
  },
  {
    path: '/calendar',
    label: 'Календарь',
    summary: 'Календарь на месяц с подробностями дня и тепловая карта за год.',
    plannedIn: 'Этап 6',
  },
  {
    path: '/habits',
    label: 'Привычки',
    summary: 'Привычки: важность, способ учёта, единицы измерения и расписание.',
    plannedIn: 'Этап 2',
  },
  {
    path: '/areas',
    label: 'Сферы',
    summary: 'Сферы жизни для группировки привычек: названия, цвета и архив.',
    plannedIn: 'Этап 2',
  },
  {
    path: '/insights',
    label: 'Инсайты',
    summary: 'Связи в ваших данных с подтверждениями и учётом задержки эффекта.',
    plannedIn: 'Этап 8',
  },
  {
    path: '/experiments',
    label: 'Эксперименты',
    summary: 'Личные эксперименты со сравнением показателей до, во время и после.',
    plannedIn: 'Этап 10',
  },
  {
    path: '/records',
    label: 'Рекорды',
    summary: 'Личные рекорды, достижения и серии пропусков.',
    plannedIn: 'Этап 11',
  },
  {
    path: '/settings',
    label: 'Настройки',
    summary: 'Хранение данных, резервные копии, экспорт в Excel и восстановление.',
    plannedIn: 'Этап 12',
  },
]
