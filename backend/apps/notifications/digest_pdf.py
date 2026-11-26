import io
from datetime import date
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_daily_digest_pdf(firm_name: str, digest_date: date, stats: dict, due_tasks: list, overdue_tasks: list) -> bytes:
    """
    Builds a professional branded Daily Digest PDF (§7.3).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#065f46'),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=15
    )
    section_style = ParagraphStyle(
        'SectionH',
        parent=styles['Heading2'],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=12,
        spaceAfter=6
    )
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, leading=10)
    cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontSize=8, leading=10, fontName='Helvetica-Bold')

    story = []

    # Title & Subtitle
    story.append(Paragraph(f"FirmFlow Daily Practice Digest", title_style))
    story.append(Paragraph(f"{firm_name} • Date: {digest_date.strftime('%d %B %Y')}", subtitle_style))

    # Metric summary table
    summary_data = [
        [
            Paragraph("Due Today", cell_bold),
            Paragraph("Overdue", cell_bold),
            Paragraph("Created Yest.", cell_bold),
            Paragraph("Completed Yest.", cell_bold),
            Paragraph("Issues Open", cell_bold),
        ],
        [
            Paragraph(str(stats.get('due_today', 0)), title_style),
            Paragraph(str(stats.get('overdue', 0)), title_style),
            Paragraph(str(stats.get('tasks_created', 0)), title_style),
            Paragraph(str(stats.get('tasks_completed', 0)), title_style),
            Paragraph(str(stats.get('issues_raised', 0)), title_style),
        ]
    ]
    t_summary = Table(summary_data, colWidths=[108, 108, 108, 108, 108])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 15))

    # Overdue Tasks Section
    story.append(Paragraph("⚠️ Overdue Compliance Tasks", section_style))
    overdue_rows = [[
        Paragraph("Task #", cell_bold),
        Paragraph("Client", cell_bold),
        Paragraph("Type", cell_bold),
        Paragraph("Due Date", cell_bold),
        Paragraph("Assignee", cell_bold),
    ]]
    for t in overdue_tasks[:15]:
        overdue_rows.append([
            Paragraph(t.task_number, cell_style),
            Paragraph(t.client.name[:25], cell_style),
            Paragraph(t.task_type_name_snapshot[:20], cell_style),
            Paragraph(str(t.due_date), cell_style),
            Paragraph(t.assigned_user.full_name if t.assigned_user else "Unassigned", cell_style),
        ])
    if len(overdue_rows) == 1:
        overdue_rows.append([Paragraph("No overdue tasks. All clear!", cell_style), "", "", "", ""])

    t_overdue = Table(overdue_rows, colWidths=[90, 150, 120, 80, 100])
    t_overdue.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fef2f2')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#fca5a5')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#fee2e2')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_overdue)
    story.append(Spacer(1, 15))

    # Tasks Due Today Section
    story.append(Paragraph("📅 Tasks Due Today", section_style))
    due_rows = [[
        Paragraph("Task #", cell_bold),
        Paragraph("Client", cell_bold),
        Paragraph("Type", cell_bold),
        Paragraph("Assignee", cell_bold),
        Paragraph("Status", cell_bold),
    ]]
    for t in due_tasks[:15]:
        due_rows.append([
            Paragraph(t.task_number, cell_style),
            Paragraph(t.client.name[:25], cell_style),
            Paragraph(t.task_type_name_snapshot[:20], cell_style),
            Paragraph(t.assigned_user.full_name if t.assigned_user else "Unassigned", cell_style),
            Paragraph(t.status.capitalize(), cell_style),
        ])
    if len(due_rows) == 1:
        due_rows.append([Paragraph("No tasks due today.", cell_style), "", "", "", ""])

    t_due = Table(due_rows, colWidths=[90, 150, 120, 100, 80])
    t_due.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fffbeb')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#fcd34d')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#fef3c7')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_due)

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data
