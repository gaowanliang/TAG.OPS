"""FastHTML 页面视图（HTML 结构）。"""
from __future__ import annotations

from fasthtml.common import (
    Aside,
    Button,
    Datalist,
    Div,
    Form,
    H1,
    H2,
    H3,
    Header,
    Input,
    Label,
    Link,
    Main,
    Option,
    P,
    Progress,
    Script,
    Section,
    Select,
    Span,
    Title,
)


# ------------------------------------------------------------------ shared
def head_links():
    """页面 <head> 中注入的静态资源。"""
    return (
        Title("TAG.OPS"),
        Link(rel="stylesheet", href="/style.css"),
        # Font Awesome 7（纯 CSS，无需 JS 初始化）
        Link(
            rel="stylesheet",
            href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@7/css/all.min.css",
        ),
        Script(src="/app.js", defer=True),
    )


# ------------------------------------------------------------------ brand
def _brand():
    return Div(
        Div(
            H1("TAG", Span(".OPS", cls="brand-accent")),
            P("WD14 · ONNX RUNTIME"),
            cls="brand-text",
        ),
        Span("v1.0", cls="brand-chip"),
        cls="sidebar-brand",
    )


# ------------------------------------------------------------------ cards
def _about_card():
    """About / links — GitHub + QQ 群。

    用 <a target="_blank" rel="noopener"> 新开标签页；QQ 群链接走 qm.qq.com，
    在 PC 端会触发 QQ 客户端协议并跳到对应加群页。
    """
    return Div(
        H2("关于", **{"data-i18n": "card.about"}),
        Div(
            Span(
                Span(cls="fa-brands fa-github fa-ico"),
                cls="about-ico",
            ),
            Span("GitHub", cls="about-label"),
            cls="about-row",
            **{"data-href": "https://github.com/gaowanliang/TAG.OPS"},
        ),
        Div(
            Span(
                Span(cls="fa-brands fa-qq fa-ico"),
                cls="about-ico",
            ),
            Span("QQ 群 · 哔哩哔哩科技宅", cls="about-label",
                 **{"data-i18n": "about.qq"}),
            cls="about-row",
            **{"data-href": "https://qm.qq.com/q/5QCcsP64WQ"},
        ),
        cls="card about-card",
    )


def _hardware_card():
    return Div(
        H2("硬件状态", **{"data-i18n": "card.hw"}),
        Div(id="hw", cls="hw-box"),
        cls="card",
    )


def _path_card():
    return Div(
        H2("图片来源", **{"data-i18n": "card.src"}),
        Div(
            Label("文件夹路径", **{"data-i18n": "label.folder"}),
            Div(
                Input(
                    id="folder-path", name="path",
                    list="recent-paths",
                    placeholder=r"例如 D:\images\anime",
                    autocomplete="off",
                    **{"data-i18n-ph": "ph.folder"},
                ),
                Datalist(id="recent-paths"),
                Button("浏览…", id="btn-browse", type="button", cls="secondary",
                       **{"data-i18n": "btn.browse"}),
                cls="path-wrap",
            ),
        ),
        Div(
            Div(
                Label("递归子目录", **{"data-i18n": "label.recursive"}),
                Select(
                    Option("是", value="1", selected=True,
                           **{"data-i18n": "opt.yes"}),
                    Option("否", value="0", **{"data-i18n": "opt.no"}),
                    id="recursive", name="recursive",
                ),
            ),
            cls="row",
        ),
        Div(id="scan-info", cls="mono", style="margin-top:6px"),
        Div(
            Div("OR · 拖放图片到页面任意位置", cls="or-label",
                **{"data-i18n": "label.or_drop"}),
            Form(
                Button("选择文件…", id="btn-pick-files", type="button", cls="secondary",
                       **{"data-i18n": "btn.pick"}),
                Input(
                    type="file", id="files", name="files",
                    multiple=True, accept="image/*",
                    style="display:none",
                ),
                Div(id="dropzone-count", cls="mono",
                    style="margin-top:6px;text-align:center"),
                id="upload-form",
            ),
            cls="upload-subcard",
        ),
        cls="card",
    )


def _settings_card():
    return Div(
        H2("识别设置", **{"data-i18n": "card.settings"}),
        Div(
            Label("模型", **{"data-i18n": "label.model"}),
            Select(id="model", name="model"),
            Div(id="model-hint", cls="model-hint"),
        ),
        Div(
            Label("加速显卡", **{"data-i18n": "label.gpu"}),
            Select(id="gpu-device", name="device_id"),
            cls="",
        ),
        Div(
            Div(
                Label("阈值", **{"data-i18n": "label.threshold"}),
                Input(
                    type="number", id="threshold", name="threshold",
                    value="0.35", step="0.05", min="0", max="1",
                ),
            ),
            Div(
                Label("最大标签数", **{"data-i18n": "label.max_tags"}),
                Input(
                    type="number", id="max-tags", name="max_tags",
                    value="50", step="1", min="1", max="500",
                ),
            ),
            cls="row",
        ),
        Div(
            Div(
                Label("替换下划线", **{"data-i18n": "label.repl_us"}),
                Select(
                    Option("是", value="1", selected=True, **{"data-i18n": "opt.yes"}),
                    Option("否", value="0", **{"data-i18n": "opt.no"}),
                    id="replace-underscore", name="replace_underscore",
                ),
            ),
            Div(
                Label("按字母排序", **{"data-i18n": "label.sort_alpha"}),
                Select(
                    Option("否", value="0", selected=True, **{"data-i18n": "opt.no"}),
                    Option("是", value="1", **{"data-i18n": "opt.yes"}),
                    id="sort-alphabetical", name="sort_alphabetical",
                ),
            ),
            cls="row",
        ),
        cls="card",
    )


def _progress_card():
    return None  # 已迁移到底部 navbar


# ------------------------------------------------------------------ bottom bar
def _bottom_bar():
    return Div(
        Div(
            Div(
                Span("PROGRESS", cls="bottom-label"),
                Span(id="pmsg", cls="mono"),
                cls="bottom-progress-head",
            ),
            Progress(id="progress", value="0", max="1"),
            cls="bottom-progress",
        ),
        Div(
            Button("识别", id="btn-run", type="button",
                   **{"data-i18n": "btn.run"}),
            cls="bottom-actions",
        ),
        cls="app-bottom",
    )


# ------------------------------------------------------------------ tabs & sections
def _grid_section():
    return Section(
        Div(
            Span(id="grid-count", cls="mono"),
            Div(
                Label("每页", **{"data-i18n": "label.page_size"}),
                Select(
                    Option("20", value="20", selected=True),
                    Option("40", value="40"),
                    Option("80", value="80"),
                    id="page-size",
                ),
                cls="page-size-wrap",
            ),
            Div(id="pager", cls="pager"),
            Div(
                Span("保存：", cls="save-label mono",
                     **{"data-i18n": "label.save_as"}),
                Button("TXT", id="btn-save-txt", type="button", cls="secondary",
                       title="保存为 .txt"),
                Button("JSON", id="btn-save-json", type="button",
                       title="保存为 .json"),
                id="save-settings",
                cls="save-settings",
                hidden=True,
            ),
            cls="grid-toolbar",
        ),
        Div(id="grid", cls="grid"),
        id="view-grid",
        cls="view-section",
    )


def _history_section():
    return Section(
        Div(
            H3("识别历史", **{"data-i18n": "h.history"}),
            Div(
                Button("刷新", id="btn-history-refresh", type="button",
                       cls="secondary", **{"data-i18n": "btn.refresh"}),
                cls="history-head-actions",
            ),
            cls="history-head",
        ),
        Div(
            Span(
                Span(cls="fa-solid fa-circle-info"),
                cls="hist-hint-icon",
            ),
            Span("所有已完成的文件夹识别都会记录在此，点击任意条目即可回看。",
                 **{"data-i18n": "info.hist_hint"}),
            cls="history-hint",
        ),
        Div(id="history-list", cls="history-list"),
        id="view-history",
        cls="view-section",
        hidden=True,
    )


def _category_section():
    return Section(
        Div(
            Div(
                Label("前 N 个标签", **{"data-i18n": "label.top_n"}),
                Input(type="number", id="top-n", value="3", min="1", max="10"),
            ),
            Div(
                Label("最小图片数", **{"data-i18n": "label.min_images"}),
                Input(type="number", id="min-images", value="2", min="1", max="100"),
            ),
            Div(
                Label("搜索", **{"data-i18n": "label.search"}),
                Input(type="text", id="cat-search", placeholder="标签名",
                      **{"data-i18n-ph": "ph.tag"}),
            ),
            Div(
                Label("排序", **{"data-i18n": "label.sort"}),
                Select(
                    Option("图片数量", value="count", selected=True,
                           **{"data-i18n": "opt.sort_count"}),
                    Option("标签名称", value="name", **{"data-i18n": "opt.sort_name"}),
                    id="cat-sort",
                ),
            ),
            Div(
                Label("\u00a0"),
                Button("刷新分类", id="btn-categorize",
                       type="button", cls="secondary",
                       **{"data-i18n": "btn.refresh_cat"}),
            ),
            id="cat-controls",
            cls="row",
        ),
        Div(id="cat-stats", cls="cat-stats"),
        Div(id="cat-grid", cls="grid"),
        id="view-category",
        cls="view-section",
        hidden=True,
    )


def _detail_section():
    return Section(
        Div(
            Button(
                Span(cls="fa-solid fa-arrow-left"),
                Span("返回", **{"data-i18n": "btn.back.label"}),
                id="btn-back", type="button", cls="secondary btn-with-icon",
                **{"data-i18n-title": "btn.back"},
            ),
            H3(id="detail-title"),
            cls="detail-header",
        ),
        Div(
            Div(
                Div(id="detail-image", cls="detail-image-wrap"),
                Div(
                    H3("图片信息", **{"data-i18n": "h.img_info"}),
                    Div(id="detail-info"),
                    cls="detail-info-block",
                ),
                cls="detail-left",
            ),
            Div(
                Div(
                    H3("评级", **{"data-i18n": "h.ratings"}),
                    Div(id="detail-ratings", cls="rating-chips"),
                    cls="detail-block detail-rating-block",
                ),
                Div(
                    Div(
                        H3("标签", **{"data-i18n": "h.tags"}),
                        Span(id="detail-tag-count", cls="tag-count-badge mono"),
                        cls="detail-block-head",
                    ),
                    Div(id="detail-tags", cls="tag-bars"),
                    cls="detail-block detail-tags-block",
                ),
                Div(
                    Button("下载全部标签", id="btn-dl-all", type="button",
                           **{"data-i18n": "btn.dl_all"}),
                    Button("下载高置信度 (≥0.7)", id="btn-dl-high",
                           type="button", cls="secondary",
                           **{"data-i18n": "btn.dl_high"}),
                    cls="detail-actions",
                ),
                cls="detail-right",
            ),
            cls="detail-body",
        ),
        id="view-detail",
        cls="view-section",
        hidden=True,
    )


# ------------------------------------------------------------------ topbar
def _topbar():
    """波普 + 孟菲斯：白底卡片条；中部嵌入视图切换 tabs。"""
    return Header(
        # 背景装饰点
        Div(cls="topbar-bg"),
        # 左：品牌 tile
        Div(
            Div("▲", cls="topbar-tile"),
            Div(
                H1(
                    Span("TAG", cls="brand-title"),
                    Span(".OPS", cls="brand-accent"),
                ),
                Div(
                    Span("NEURAL", cls="brand-kw"),
                    Span("·", cls="brand-dot"),
                    Span("TAGGER", cls="brand-kw"),
                    Span("·", cls="brand-dot"),
                    Span("CAMIE", cls="brand-kw"),
                    Span("·", cls="brand-dot"),
                    Span("WD14", cls="brand-kw"),
                    cls="brand-sub",
                ),
                cls="topbar-text",
            ),
            cls="topbar-brand",
        ),
        # 中：视图切换 tabs
        Div(
            Button(
                Span(cls="tab-ico fa-solid fa-table-cells-large"),
                Span("图片网格", cls="tab-label", **{"data-i18n": "tab.grid"}),
                id="tab-grid", cls="tab active", type="button",
            ),
            Button(
                Span(cls="tab-ico fa-solid fa-tags"),
                Span("标签分类", cls="tab-label", **{"data-i18n": "tab.cat"}),
                id="tab-category", cls="tab", type="button",
            ),
            Button(
                Span(cls="tab-ico fa-solid fa-clock-rotate-left"),
                Span("历史", cls="tab-label", **{"data-i18n": "tab.hist"}),
                id="tab-history", cls="tab", type="button",
            ),
            cls="topbar-tabs",
        ),
        # 右：滑动式语言切换（类似老式滑盖手机，中/EN 上下排列）
        Div(
            Div(
                Span("中", cls="lang-slot lang-zh active", **{"data-lang": "zh"}),
                Span("EN", cls="lang-slot lang-en", **{"data-lang": "en"}),
                Span(cls="lang-thumb"),
                id="btn-lang",
                cls="lang-slider",
                title="Language / 语言",
                role="button",
                tabindex="0",
            ),
            cls="topbar-lang",
        ),
        cls="app-topbar",
    )


# ------------------------------------------------------------------ page
def _browser_modal():
    return Div(
        Div(
            Div(
                H3("选择文件夹", **{"data-i18n": "h.pick_folder"}),
                Button(
                    Span(cls="fa-solid fa-xmark"),
                    id="browser-close", type="button", cls="secondary icon-btn",
                ),
                cls="browser-header",
            ),
            Div(
                Button(
                    Span(cls="fa-solid fa-arrow-up"),
                    Span("上级", **{"data-i18n": "btn.up.label"}),
                    id="browser-up", type="button",
                    cls="secondary btn-with-icon",
                ),
                Input(id="browser-path", type="text", placeholder="当前路径",
                      **{"data-i18n-ph": "ph.cur_path"}),
                Button("前往", id="browser-go", type="button", cls="secondary",
                       **{"data-i18n": "btn.go"}),
                cls="browser-toolbar",
            ),
            Div(id="browser-list", cls="browser-list"),
            Div(
                Button("取消", id="browser-cancel", type="button", cls="secondary",
                       **{"data-i18n": "btn.cancel"}),
                Button("选择此文件夹", id="browser-pick", type="button",
                       **{"data-i18n": "btn.pick_this"}),
                cls="browser-footer",
            ),
            cls="browser-dialog",
        ),
        id="browser-modal",
        cls="browser-modal",
        hidden=True,
    )


def _dialog_modal():
    return Div(
        Div(
            Div(H3(id="dialog-title"), cls="dialog-header"),
            Div(id="dialog-body", cls="dialog-body"),
            Div(id="dialog-footer", cls="dialog-footer"),
            cls="dialog",
        ),
        id="dialog-modal",
        cls="browser-modal",
        hidden=True,
    )


def _drop_overlay():
    return Div(
        Div(
            Span(
                Span(cls="fa-solid fa-cloud-arrow-up"),
                cls="drop-overlay-icon",
            ),
            Div("拖放图片到此处", cls="drop-overlay-title",
                **{"data-i18n": "drop.title"}),
            Div("松开即可添加", cls="drop-overlay-sub mono",
                **{"data-i18n": "drop.sub"}),
            cls="drop-overlay-inner",
        ),
        id="drop-overlay",
        cls="drop-overlay",
        hidden=True,
    )


def home_page():
    return Main(
        _topbar(),
        Aside(
            Div(
                _hardware_card(),
                _path_card(),
                _settings_card(),
                _about_card(),
                cls="sidebar-scroll",
            ),
            cls="app-sidebar",
        ),
        Section(
            Div(
                _grid_section(),
                _category_section(),
                _history_section(),
                _detail_section(),
                cls="main-scroll",
            ),
            cls="app-main",
        ),
        _bottom_bar(),
        _browser_modal(),
        _dialog_modal(),
        _drop_overlay(),
        cls="app-shell",
    )
