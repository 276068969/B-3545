import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from django.utils import timezone
from django.http import HttpResponse
from collections import defaultdict


ERROR_TYPE_TIME_FORMAT = 'time_format'
ERROR_TYPE_PLAYER_MISSING = 'player_missing'
ERROR_TYPE_SCORE_IMBALANCE = 'score_imbalance'
ERROR_TYPE_INSUFFICIENT_PLAYERS = 'insufficient_players'
ERROR_TYPE_SCORE_FORMAT = 'score_format'
ERROR_TYPE_PARSE_ERROR = 'parse_error'

ERROR_TYPE_LABELS = {
    ERROR_TYPE_TIME_FORMAT: '时间格式异常',
    ERROR_TYPE_PLAYER_MISSING: '玩家缺失',
    ERROR_TYPE_SCORE_IMBALANCE: '分数不平衡',
    ERROR_TYPE_INSUFFICIENT_PLAYERS: '玩家数量不足',
    ERROR_TYPE_SCORE_FORMAT: '得分格式错误',
    ERROR_TYPE_PARSE_ERROR: '解析错误',
}


class ImportErrorItem:
    def __init__(self, row_num, message, error_type, details=None):
        self.row_num = row_num
        self.message = message
        self.error_type = error_type
        self.details = details or {}

    def to_dict(self):
        return {
            'row_num': self.row_num,
            'message': self.message,
            'error_type': self.error_type,
            'error_type_label': ERROR_TYPE_LABELS.get(self.error_type, '其他错误'),
            'details': self.details,
        }


class ImportResult:
    def __init__(self):
        self.games_data = []
        self.errors = []
        self._error_groups = defaultdict(list)

    def add_error(self, error_item):
        self.errors.append(error_item)
        self._error_groups[error_item.error_type].append(error_item)

    @property
    def success_count(self):
        return len(self.games_data)

    @property
    def error_count(self):
        return len(self.errors)

    @property
    def total_count(self):
        return self.success_count + self.error_count

    def get_errors_by_type(self, error_type):
        return self._error_groups.get(error_type, [])

    def get_error_summary(self):
        groups = []
        for error_type, label in ERROR_TYPE_LABELS.items():
            errors = self._error_groups.get(error_type, [])
            if errors:
                groups.append({
                    'error_type': error_type,
                    'label': label,
                    'count': len(errors),
                    'errors': [e.to_dict() for e in errors],
                })
        other_errors = [
            e for e in self.errors
            if e.error_type not in ERROR_TYPE_LABELS
        ]
        if other_errors:
            groups.append({
                'error_type': 'other',
                'label': '其他错误',
                'count': len(other_errors),
                'errors': [e.to_dict() for e in other_errors],
            })
        return groups

    def get_summary_dict(self):
        return {
            'total': self.total_count,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'error_groups': self.get_error_summary(),
        }

    def get_flat_errors(self):
        return [e.to_dict() for e in self.errors]

    def get_error_messages(self):
        return [e.message for e in self.errors]


def export_games_to_pdf(games_qs, view_mode='score'):
    """Export games queryset to PDF file using reportlab"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    # Try to register a CJK font; fall back to built-in if unavailable
    font_name = 'Helvetica'
    cjk_fonts = [
        # Debian/Ubuntu (installed via fonts-wqy-microhei)
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        # Debian Noto CJK
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf',
        # macOS
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        # Windows
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simsun.ttc',
    ]
    for fp in cjk_fonts:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont('CJK', fp))
                font_name = 'CJK'
                break
            except Exception:
                pass

    if font_name == 'Helvetica':
        # No CJK font available – return a plain text notice
        response = HttpResponse(
            '系统未安装中文字体，无法导出 PDF。请联系管理员在服务器上安装 fonts-wqy-microhei 后重试。',
            content_type='text/plain; charset=utf-8'
        )
        return response

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', fontName=font_name, fontSize=16, spaceAfter=8,
                                  textColor=colors.HexColor('#c9a227'), alignment=1)
    subtitle_style = ParagraphStyle('Sub', fontName=font_name, fontSize=9, spaceAfter=12,
                                     textColor=colors.grey, alignment=1)
    cell_style = ParagraphStyle('Cell', fontName=font_name, fontSize=8)

    elements = []
    if view_mode == 'amount':
        title_text = '麻将战绩报告（金额）'
    else:
        title_text = '麻将战绩报告'
    elements.append(Paragraph(title_text, title_style))
    elements.append(Paragraph(
        f'导出时间：{timezone.now().strftime("%Y-%m-%d %H:%M")}  共 {games_qs.count()} 场',
        subtitle_style
    ))
    elements.append(Spacer(1, 4 * mm))

    if view_mode == 'amount':
        headers = ['#', '游戏时间', '地点', '类型', '底分(元/分)', '参与玩家 & 金额(元)', '备注']
    else:
        headers = ['#', '游戏时间', '地点', '类型', '底分', '参与玩家 & 得分', '备注']
    table_data = [headers]

    for i, game in enumerate(games_qs[:500], 1):
        players = game.players.select_related('user').order_by('-score')
        if view_mode == 'amount':
            player_str = '  '.join(
                f"{p.user.get_display_name()}:{'+' if p.score >= 0 else ''}{p.score * game.base_score}元"
                for p in players
            )
        else:
            player_str = '  '.join(
                f"{p.user.get_display_name()}:{'+' if p.score >= 0 else ''}{p.score}"
                for p in players
            )
        row = [
            str(i),
            game.game_time.strftime('%Y-%m-%d %H:%M'),
            game.location or '-',
            game.get_game_type_display(),
            str(game.base_score),
            Paragraph(player_str, cell_style),
            Paragraph(game.notes[:40] if game.notes else '-', cell_style),
        ]
        table_data.append(row)

    col_widths = [10*mm, 38*mm, 30*mm, 28*mm, 16*mm, 100*mm, 45*mm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a3240')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#c9a227')),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f8fb')]),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('ROWHEIGHT', (0, 0), (-1, 0), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    if view_mode == 'amount':
        filename = f'mahjong_records_amount_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    else:
        filename = f'mahjong_records_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def export_games_to_excel(games_qs, view_mode='score'):
    """Export games queryset to Excel file"""
    wb = openpyxl.Workbook()
    ws = wb.active
    if view_mode == 'amount':
        ws.title = '麻将战绩(金额)'
    else:
        ws.title = '麻将战绩'

    # Styles
    header_font = Font(name='微软雅黑', bold=True, color='FFFFFF', size=12)
    header_fill = PatternFill(start_color='1a3240', end_color='1a3240', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    if view_mode == 'amount':
        headers = ['游戏ID', '游戏时间', '地点', '游戏类型', '底分(元/分)', '参与玩家', '各玩家金额(元)', '是否补录', '备注']
    else:
        headers = ['游戏ID', '游戏时间', '地点', '游戏类型', '底分', '参与玩家', '各玩家得分', '是否补录', '备注']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    ws.row_dimensions[1].height = 25

    for row, game in enumerate(games_qs, 2):
        players = game.players.select_related('user').order_by('-score')
        player_names = ', '.join([p.user.get_display_name() for p in players])
        if view_mode == 'amount':
            player_scores = ', '.join([f'{p.user.get_display_name()}:{p.score * game.base_score}' for p in players])
        else:
            player_scores = ', '.join([f'{p.user.get_display_name()}:{p.score}' for p in players])

        row_data = [
            game.pk,
            game.game_time.strftime('%Y-%m-%d %H:%M'),
            game.location or '',
            game.get_game_type_display(),
            game.base_score,
            player_names,
            player_scores,
            '是' if game.is_supplemental else '否',
            game.notes or '',
        ]

        for col, value in enumerate(row_data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = thin_border
            if row % 2 == 0:
                cell.fill = PatternFill(start_color='f0f8ff', end_color='f0f8ff', fill_type='solid')

    # Auto-width columns
    col_widths = [10, 18, 15, 15, 8, 25, 35, 10, 20]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    if view_mode == 'amount':
        filename = f'mahjong_records_amount_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    else:
        filename = f'mahjong_records_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


def get_import_template():
    """Generate Excel import template"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '战绩导入模板'

    headers = ['游戏时间(YYYY-MM-DD HH:MM)', '地点', '游戏类型', '底分', '玩家1用户名', '玩家1得分',
               '玩家2用户名', '玩家2得分', '玩家3用户名', '玩家3得分', '玩家4用户名', '玩家4得分', '备注']

    header_font = Font(name='微软雅黑', bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='c9a227', end_color='c9a227', fill_type='solid')

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    example_rows = [
        ['2024-01-15 19:30', '家里', 'mahjong_16', '1',
         'zhangsan', '30', 'lisi', '-10', 'wangwu', '-10', 'zhaoliu', '-10', '示例数据'],
        ['2024-01-16 20:00', '茶馆', 'mahjong_16', '2',
         'zhangsan', '-20', 'lisi', '40', 'wangwu', '-10', '', '', ''],
    ]
    for row_idx, example_row in enumerate(example_rows, 2):
        for col, value in enumerate(example_row, 1):
            ws.cell(row=row_idx, column=col, value=value)

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 20

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="mahjong_import_template.xlsx"'
    wb.save(response)
    return response


def _parse_rows(rows_iter, start_row=2):
    """Parse iterable of row tuples into game data (shared by Excel and CSV parsers)

    Returns:
        ImportResult: 结构化的导入结果，包含成功数据和分类错误
    """
    result = ImportResult()
    from apps.accounts.models import User
    from datetime import datetime

    for row_num, row in enumerate(rows_iter, start_row):
        if not any(row):
            continue
        try:
            game_time_str = str(row[0]).strip() if row[0] else ''
            location = str(row[1]).strip() if row[1] else ''
            game_type = str(row[2]).strip() if row[2] else 'mahjong_16'
            base_score = int(row[3]) if row[3] else 1
            notes = str(row[12]).strip() if len(row) > 12 and row[12] else ''

            try:
                if isinstance(row[0], datetime):
                    game_time = timezone.make_aware(row[0])
                else:
                    game_time = timezone.make_aware(datetime.strptime(game_time_str, '%Y-%m-%d %H:%M'))
            except ValueError:
                result.add_error(ImportErrorItem(
                    row_num=row_num,
                    message=f'第{row_num}行：时间格式错误 "{game_time_str}"',
                    error_type=ERROR_TYPE_TIME_FORMAT,
                    details={'game_time_str': game_time_str},
                ))
                continue

            players_data = []
            total_score = 0
            has_score_format_error = False
            missing_players = []
            for i in range(4):
                username_col = 4 + i * 2
                score_col = 5 + i * 2
                if len(row) > score_col and row[username_col]:
                    username = str(row[username_col]).strip()
                    try:
                        score = int(row[score_col]) if row[score_col] is not None else 0
                    except (ValueError, TypeError):
                        result.add_error(ImportErrorItem(
                            row_num=row_num,
                            message=f'第{row_num}行：玩家{i+1}得分格式错误',
                            error_type=ERROR_TYPE_SCORE_FORMAT,
                            details={'player_index': i + 1, 'username': username},
                        ))
                        has_score_format_error = True
                        score = 0
                    try:
                        user = User.objects.get(username=username)
                        players_data.append({'user': user, 'score': score})
                        total_score += score
                    except User.DoesNotExist:
                        missing_players.append(username)
                        result.add_error(ImportErrorItem(
                            row_num=row_num,
                            message=f'第{row_num}行：用户 "{username}" 不存在',
                            error_type=ERROR_TYPE_PLAYER_MISSING,
                            details={'username': username},
                        ))

            if len(players_data) < 2:
                if not missing_players and not has_score_format_error:
                    result.add_error(ImportErrorItem(
                        row_num=row_num,
                        message=f'第{row_num}行：至少需要2名玩家',
                        error_type=ERROR_TYPE_INSUFFICIENT_PLAYERS,
                        details={'player_count': len(players_data)},
                    ))
                continue

            if total_score != 0:
                result.add_error(ImportErrorItem(
                    row_num=row_num,
                    message=f'第{row_num}行：得分总和不为0（当前为{total_score}）',
                    error_type=ERROR_TYPE_SCORE_IMBALANCE,
                    details={'total_score': total_score},
                ))
                continue

            result.games_data.append({
                'game_time': game_time,
                'location': location,
                'game_type': game_type,
                'base_score': base_score,
                'notes': notes,
                'players': players_data,
                'row_num': row_num,
            })
        except Exception as e:
            result.add_error(ImportErrorItem(
                row_num=row_num,
                message=f'第{row_num}行：解析错误 {str(e)}',
                error_type=ERROR_TYPE_PARSE_ERROR,
                details={'exception': str(e)},
            ))

    return result


def parse_import_file(file_obj):
    """Parse Excel or CSV import file, return ImportResult with structured data

    Returns:
        ImportResult: 结构化的导入结果，包含成功数据和分类错误
    """
    filename = getattr(file_obj, 'name', '')
    if filename.lower().endswith('.csv'):
        import csv
        try:
            content = file_obj.read()
            for enc in ('utf-8-sig', 'utf-8', 'gb18030', 'gbk'):
                try:
                    text = content.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                result = ImportResult()
                result.add_error(ImportErrorItem(
                    row_num=0,
                    message='CSV文件编码无法识别，请另存为UTF-8编码后再导入',
                    error_type=ERROR_TYPE_PARSE_ERROR,
                ))
                return result
            reader = csv.reader(text.splitlines())
            rows = list(reader)
            if not rows:
                result = ImportResult()
                result.add_error(ImportErrorItem(
                    row_num=0,
                    message='CSV文件为空',
                    error_type=ERROR_TYPE_PARSE_ERROR,
                ))
                return result
            data_rows = [tuple(r) for r in rows[1:]]
            return _parse_rows(iter(data_rows))
        except Exception as e:
            result = ImportResult()
            result.add_error(ImportErrorItem(
                row_num=0,
                message=f'CSV文件解析失败：{str(e)}',
                error_type=ERROR_TYPE_PARSE_ERROR,
            ))
            return result

    try:
        wb = openpyxl.load_workbook(file_obj)
        ws = wb.active
    except Exception as e:
        result = ImportResult()
        result.add_error(ImportErrorItem(
            row_num=0,
            message=f'文件格式错误：{str(e)}',
            error_type=ERROR_TYPE_PARSE_ERROR,
        ))
        return result

    return _parse_rows(ws.iter_rows(min_row=2, values_only=True))


def apply_game_filters(queryset, form):
    """Apply filter form to games queryset"""
    if not form.is_valid():
        return queryset

    from django.utils import timezone
    from datetime import timedelta, datetime

    data = form.cleaned_data
    date_range = data.get('date_range')
    now = timezone.now()

    if date_range == 'today':
        queryset = queryset.filter(game_time__date=now.date())
    elif date_range == 'week':
        week_start = now - timedelta(days=now.weekday())
        queryset = queryset.filter(game_time__gte=week_start.replace(hour=0, minute=0, second=0))
    elif date_range == 'month':
        queryset = queryset.filter(game_time__year=now.year, game_time__month=now.month)
    elif date_range == 'custom':
        if data.get('date_from'):
            queryset = queryset.filter(game_time__date__gte=data['date_from'])
        if data.get('date_to'):
            queryset = queryset.filter(game_time__date__lte=data['date_to'])

    if data.get('player'):
        queryset = queryset.filter(players__user=data['player'])

    if data.get('game_type'):
        queryset = queryset.filter(game_type=data['game_type'])

    if data.get('is_supplemental') != '':
        is_supp = data.get('is_supplemental') == '1'
        if data.get('is_supplemental'):
            queryset = queryset.filter(is_supplemental=is_supp)

    if data.get('search'):
        from django.db.models import Q
        search = data['search']
        queryset = queryset.filter(
            Q(location__icontains=search) | Q(notes__icontains=search)
        )

    return queryset
