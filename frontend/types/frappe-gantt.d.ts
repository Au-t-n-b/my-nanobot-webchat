declare module "frappe-gantt" {
  export type FrappeGanttTask = {
    id: string;
    name: string;
    start: string;
    end: string;
    progress?: number;
    dependencies?: string;
    custom_class?: string;
    [key: string]: unknown;
  };

  export type FrappeViewMode = {
    name: string;
    step: string;
    padding?: string;
    lower_text?: string | ((currentDate: Date, previousDate: Date | null, lang: string) => string);
    upper_text?: string | ((currentDate: Date, previousDate: Date | null, lang: string) => string);
    upper_text_frequency?: number;
    thick_line?: (currentDate: Date) => boolean;
    column_width?: number;
    date_format?: string;
    snap_at?: string;
  };

  export type FrappePopupContext = {
    task: FrappeGanttTask;
    chart: Gantt;
    get_title: () => HTMLElement;
    get_subtitle: () => HTMLElement;
    get_details: () => HTMLElement;
    set_title: (html: string) => void;
    set_subtitle: (html: string) => void;
    set_details: (html: string) => void;
    add_action: (html: string, fn: () => void) => void;
  };

  export type GanttOptions = {
    view_mode?: string | FrappeViewMode;
    view_modes?: FrappeViewMode[];
    view_mode_select?: boolean;
    today_button?: boolean;
    scroll_to?: "today" | "start" | "end" | string;
    popup_on?: "hover" | "click";
    popup?: false | ((context: FrappePopupContext) => string | void | false);
    readonly?: boolean;
    readonly_dates?: boolean;
    readonly_progress?: boolean;
    column_width?: number;
    bar_height?: number;
    bar_corner_radius?: number;
    container_height?: number | "auto";
    upper_header_height?: number;
    lower_header_height?: number;
    padding?: number;
    lines?: "none" | "vertical" | "horizontal" | "both";
    language?: string;
    date_format?: string;
    move_dependencies?: boolean;
    auto_move_label?: boolean;
    infinite_padding?: boolean;
  };

  export default class Gantt {
    constructor(selector: string | HTMLElement, tasks: FrappeGanttTask[], options?: GanttOptions);
    refresh(tasks: FrappeGanttTask[]): void;
    update_options(options: Partial<GanttOptions>): void;
    change_view_mode(viewMode?: string | FrappeViewMode, maintain_pos?: boolean): void;
    scroll_current(): void;
  }
}
