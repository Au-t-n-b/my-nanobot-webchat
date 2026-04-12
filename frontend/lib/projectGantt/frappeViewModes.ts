import type { FrappeViewMode } from "frappe-gantt";

export type ProjectGanttViewMode = "year" | "month" | "week" | "day";

const WEEKDAY = new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" });
const MONTH = new Intl.DateTimeFormat("zh-CN", { month: "short" });
const YEAR = new Intl.DateTimeFormat("zh-CN", { year: "numeric" });

function weekLowerText(currentDate: Date) {
  return WEEKDAY.format(currentDate);
}

function monthLowerText(currentDate: Date) {
  return `${currentDate.getMonth() + 1}/${currentDate.getDate()}`;
}

function upperByMonth(currentDate: Date, previousDate: Date | null) {
  if (!previousDate || previousDate.getMonth() !== currentDate.getMonth()) {
    return MONTH.format(currentDate);
  }
  return "";
}

function upperByYear(currentDate: Date, previousDate: Date | null) {
  if (!previousDate || previousDate.getFullYear() !== currentDate.getFullYear()) {
    return YEAR.format(currentDate);
  }
  return "";
}

export const FRAPPE_VIEW_MODES: Record<ProjectGanttViewMode, FrappeViewMode> = {
  year: {
    name: "Year",
    step: "1m",
    padding: "1m",
    column_width: 60,
    lower_text: (currentDate) => MONTH.format(currentDate),
    upper_text: upperByYear,
    upper_text_frequency: 12,
    thick_line: (currentDate) => currentDate.getMonth() === 0,
  },
  month: {
    name: "Month",
    step: "7d",
    padding: "14d",
    column_width: 64,
    lower_text: monthLowerText,
    upper_text: upperByMonth,
    upper_text_frequency: 4,
    thick_line: (currentDate) => currentDate.getDate() <= 7,
  },
  week: {
    name: "Week",
    step: "7d",
    padding: "14d",
    column_width: 60,
    lower_text: weekLowerText,
    upper_text: upperByMonth,
    upper_text_frequency: 4,
    thick_line: (currentDate) => currentDate.getDate() <= 7,
  },
  day: {
    name: "Day",
    step: "1d",
    padding: "7d",
    column_width: 36,
    lower_text: (currentDate) => String(currentDate.getDate()).padStart(2, "0"),
    upper_text: upperByMonth,
    upper_text_frequency: 28,
    thick_line: (currentDate) => currentDate.getDay() === 1 || currentDate.getDate() === 1,
  },
};

export function getFrappeViewMode(mode: ProjectGanttViewMode) {
  return FRAPPE_VIEW_MODES[mode];
}

export function projectGanttViewModes() {
  return Object.values(FRAPPE_VIEW_MODES);
}
