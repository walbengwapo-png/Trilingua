from __future__ import annotations

import copy
import os
import random
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{%s}" % NS["w"]

REFERENCE = Path(r"C:\dev\Trilingua\.tmp_google_classroom_tests\Sample_Test Case Template.docx")
OUTPUT = Path(r"C:\dev\Trilingua\Google Classroom Student Test Cases.docx")


SCENARIOS = [
    {
        "module": "Stream - Announcements",
        "id": "TC_STR_001",
        "scenario": "Verify that students can view teacher announcements in the Stream.",
        "cases": [
            (
                "View the newest announcement.",
                "Student is enrolled; teacher posted two announcements.",
                ["Open the class.", "Select Stream.", "Locate the newest announcement."],
                "Two dated announcements with distinct text.",
                "Both announcements appear, with the newest item shown first unless the teacher moved a post.",
            ),
            (
                "Open announcement details.",
                "An announcement contains text and an attachment.",
                ["Open Stream.", "Select the announcement.", "Review the text and attachment."],
                "Announcement with a PDF or image.",
                "The full announcement text, teacher name, posting time, and attachment are visible.",
            ),
            (
                "Open an announcement attachment.",
                "The student has access to the attached resource.",
                ["Open the announcement.", "Select the attachment.", "Return to Classroom."],
                "Accessible Drive file or web link.",
                "The resource opens successfully and the student can return to the same Stream position.",
            ),
            (
                "Retain announcements after refresh.",
                "The class Stream is loaded.",
                ["Note the visible announcements.", "Refresh the browser.", "Compare the Stream."],
                "Existing Stream posts.",
                "The same authorized announcements remain visible without duplication or data loss.",
            ),
            (
                "Hide a scheduled announcement before release.",
                "Teacher scheduled an announcement for a later time.",
                ["Open Stream before release.", "Search the visible posts.", "Recheck after release time."],
                "Scheduled announcement and release time.",
                "The post is hidden before release and appears after the scheduled time.",
            ),
        ],
    },
    {
        "module": "Stream - Comments",
        "id": "TC_STR_002",
        "scenario": "Verify student class comments, replies, deletion, and permission handling.",
        "cases": [
            (
                "Post a class comment.",
                "Teacher allows students to comment on the selected post.",
                ["Select Add class comment.", "Enter the test comment.", "Select Post."],
                "Comment: Thank you for the reminder.",
                "The comment appears once with the student's name and posting time.",
            ),
            (
                "Reply to an existing comment.",
                "A classmate comment is visible and replies are allowed.",
                ["Select Reply on the comment.", "Enter a response.", "Select Post."],
                "Reply: I found the file.",
                "The reply appears under the thread and identifies or mentions the original commenter.",
            ),
            (
                "Delete the student's own comment.",
                "The student has posted a test comment.",
                ["Open the comment menu.", "Select Delete.", "Confirm deletion."],
                "Student-owned test comment.",
                "The comment is removed from the student's view after confirmation.",
            ),
            (
                "Prevent deletion of another user's comment.",
                "A teacher or classmate comment is visible.",
                ["Open the other user's comment menu.", "Review available actions."],
                "Comment owned by another class member.",
                "No student option is available to delete or edit the other user's comment.",
            ),
            (
                "Honor disabled commenting.",
                "Teacher disabled comments or muted the test student.",
                ["Open Stream.", "Open a post with comments.", "Check for comment controls."],
                "Class with restricted student commenting.",
                "Posting controls are absent or disabled and the existing Stream remains viewable.",
            ),
        ],
    },
    {
        "module": "Stream - Materials",
        "id": "TC_STR_003",
        "scenario": "Verify that students can find and open materials shared through the Stream.",
        "cases": [
            (
                "View a newly posted material.",
                "Teacher published class material to the class.",
                ["Open Stream.", "Locate the material post.", "Review its title and description."],
                "Material title, description, and posting date.",
                "The material post displays the correct title, description, teacher, and date.",
            ),
            (
                "Open a Drive material.",
                "A viewable Drive file is attached to the material.",
                ["Select the material post.", "Open the Drive attachment.", "Check access mode."],
                "View-only Google Doc, Sheet, or Slide.",
                "The correct file opens and the student's access matches the teacher's sharing setting.",
            ),
            (
                "Open an external material link.",
                "The material contains a valid HTTPS link.",
                ["Open the material.", "Select the link.", "Verify the destination."],
                "Teacher-approved website URL.",
                "The expected website opens without changing or corrupting the Classroom post.",
            ),
            (
                "Handle an unavailable attachment.",
                "The linked file was removed or access was revoked.",
                ["Open the material post.", "Select the unavailable attachment."],
                "Restricted or deleted test file.",
                "A clear access or availability message appears; Classroom remains responsive.",
            ),
            (
                "Match Stream and Classwork material.",
                "The same published material is listed in Classwork.",
                ["Note the Stream material.", "Open Classwork.", "Find the same material."],
                "Published material assigned to one topic.",
                "Title, description, attachments, and access are consistent in both locations.",
            ),
        ],
    },
    {
        "module": "Classwork - Viewing",
        "id": "TC_CWK_001",
        "scenario": "Verify that students can view assigned classwork and supporting details.",
        "cases": [
            (
                "View classwork grouped by topic.",
                "Teacher published items under multiple topics.",
                ["Open Classwork.", "Review topic sections.", "Select one topic."],
                "Two topics with assignments and materials.",
                "Published items appear under the correct topics and topic filtering shows only matching items.",
            ),
            (
                "Open assignment instructions.",
                "A published assignment is assigned to the student.",
                ["Select the assignment.", "Select View instructions or View assignment.", "Review details."],
                "Assignment with title and instructions.",
                "The correct title, instructions, teacher, and assigned status are displayed.",
            ),
            (
                "View due date and points.",
                "The assignment has a due date and point value.",
                ["Open the assignment.", "Locate due date and points.", "Compare with teacher setup."],
                "Known date, time, and point value.",
                "The student sees the correct due date, due time, time zone behavior, and points.",
            ),
            (
                "View attachments and rubric.",
                "The assignment includes resources and a rubric.",
                ["Open the assignment.", "Open each resource.", "Expand the rubric."],
                "Drive file, link, and rubric criteria.",
                "All authorized resources open and the complete rubric criteria and points are readable.",
            ),
            (
                "Hide unassigned or draft work.",
                "Teacher has a draft or work assigned to other students only.",
                ["Open Classwork as the test student.", "Search topics and the work list."],
                "Draft or individually assigned test item.",
                "The student cannot see classwork that was not published or assigned to that account.",
            ),
        ],
    },
    {
        "module": "Classwork - Submitting",
        "id": "TC_CWK_002",
        "scenario": "Verify assignment submission with files, links, and confirmation controls.",
        "cases": [
            (
                "Submit an uploaded file.",
                "Assignment accepts work; test file is available locally.",
                ["Open the assignment.", "Add or create a file.", "Select Turn in and confirm."],
                "PDF or DOCX under the allowed size.",
                "The attachment is listed and the assignment status changes to Turned in once.",
            ),
            (
                "Submit a Drive file.",
                "Student owns an accessible Drive file.",
                ["Open Your work.", "Add the Drive file.", "Turn in and confirm."],
                "Student-owned Google Doc.",
                "The selected file is attached and the teacher can receive the submitted version.",
            ),
            (
                "Mark work as done without a file.",
                "Teacher created an assignment that requires no attachment.",
                ["Open the assignment.", "Select Mark as done.", "Confirm."],
                "No-attachment assignment.",
                "The status changes to Turned in and no unexpected attachment is created.",
            ),
            (
                "Cancel submission confirmation.",
                "Work is attached but not yet submitted.",
                ["Select Turn in.", "Cancel in the confirmation dialog.", "Review the status."],
                "One attached test file.",
                "The assignment remains unsubmitted and the attachment stays available for review.",
            ),
            (
                "Handle a deadline submission.",
                "Teacher provides a controlled assignment at or after its due time.",
                ["Open the assignment near the deadline.", "Attempt to submit.", "Review status or message."],
                "Known due date and synchronized clock.",
                "Classroom follows the configured deadline behavior and clearly shows Late or a submission restriction.",
            ),
        ],
    },
    {
        "module": "Classwork - Resubmitting and Comments",
        "id": "TC_CWK_003",
        "scenario": "Verify unsubmission, resubmission, and private assignment comments.",
        "cases": [
            (
                "Unsubmit work before the due date.",
                "Assignment is Turned in and the due date has not passed.",
                ["Open the assignment.", "Select Unsubmit.", "Confirm."],
                "Previously submitted assignment.",
                "The assignment becomes editable and its status changes from Turned in to Assigned.",
            ),
            (
                "Replace work and resubmit.",
                "The student successfully unsubmitted the assignment.",
                ["Remove the old attachment.", "Add the revised file.", "Turn in and confirm."],
                "Original file and revised file.",
                "Only the intended revised work is submitted and the status returns to Turned in.",
            ),
            (
                "Preserve resubmission status after refresh.",
                "Revised work was turned in successfully.",
                ["Refresh the browser.", "Reopen the assignment.", "Check Your work."],
                "Resubmitted assignment.",
                "The Turned in state and revised attachment remain visible without duplicate files.",
            ),
            (
                "Post a private comment.",
                "The student can open the assignment details.",
                ["Enter a private comment.", "Select Post.", "Refresh the assignment."],
                "Comment: Please confirm that my revision opens.",
                "The comment appears once in the private thread and is visible only to the student and teacher.",
            ),
            (
                "View a teacher reply to a private comment.",
                "Teacher replied to the student's private comment.",
                ["Open the assignment.", "Review the private comment thread.", "Open any notification."],
                "Teacher reply in the test thread.",
                "The reply is readable, attributed to the teacher, and linked to the correct assignment.",
            ),
        ],
    },
    {
        "module": "People - Viewing and Email",
        "id": "TC_PPL_001",
        "scenario": "Verify the class roster and student email actions on the People page.",
        "cases": [
            (
                "View teachers and classmates.",
                "Student is enrolled in a class with teachers and classmates.",
                ["Open the class.", "Select People.", "Review both roster sections."],
                "Known teacher and student roster.",
                "Teachers and Students sections show the expected authorized class members.",
            ),
            (
                "Protect roster information.",
                "The People page is open with a student account.",
                ["Review visible profile details.", "Compare with account permissions."],
                "Class member names, photos, and permitted email links.",
                "Only information allowed for the student's role and school settings is displayed.",
            ),
            (
                "Send an email to a teacher.",
                "School Gmail and Directory services allow student email.",
                ["Select Email beside the teacher.", "Enter subject and message.", "Send the test email."],
                "Subject: Classroom test; approved test message.",
                "A compose window opens with the teacher addressed and the sent message appears in Sent mail.",
            ),
            (
                "Send an email to a classmate.",
                "Student-to-student email is enabled for the school account.",
                ["Select Email beside a classmate.", "Enter subject and message.", "Send the test email."],
                "Approved recipient and harmless test message.",
                "The compose window addresses the selected classmate and the email sends once.",
            ),
            (
                "Handle email when disabled.",
                "Administrator disabled Gmail or Directory access for students.",
                ["Open People.", "Review teacher and classmate actions."],
                "Student account with email disabled.",
                "Email links are absent or unavailable; the roster remains visible according to policy.",
            ),
        ],
    },
    {
        "module": "Additional Student Scenarios",
        "id": "TC_EXT_001",
        "scenario": "Verify navigation, isolation, refresh behavior, and keyboard access.",
        "cases": [
            (
                "Navigate between class tabs.",
                "The student is viewing an enrolled class.",
                ["Open Stream.", "Open Classwork.", "Open People.", "Return to Stream."],
                "One active class.",
                "Each tab loads the correct module without signing out or mixing content.",
            ),
            (
                "Keep classes isolated.",
                "The student belongs to two classes with distinct test content.",
                ["Open Class A and note content.", "Switch to Class B.", "Compare items and roster."],
                "Two classes with unique posts and members.",
                "Only the selected class's posts, work, people, and private comments are shown.",
            ),
            (
                "Reject an unauthorized class URL.",
                "Student is not enrolled in the target class.",
                ["Open the supplied direct class URL.", "Observe the response."],
                "URL for a class outside the student's access.",
                "Classroom denies access or requests a valid invitation without exposing class data.",
            ),
            (
                "Recover after browser refresh.",
                "Student is signed in and viewing an assignment.",
                ["Refresh the page.", "Use browser Back and Forward.", "Reopen the item."],
                "Valid signed-in session.",
                "The session remains valid and navigation returns to the correct authorized content.",
            ),
            (
                "Use keyboard navigation.",
                "Supported browser and keyboard-only input are available.",
                ["Press Tab through controls.", "Activate tabs and an item with Enter.", "Return with keyboard."],
                "Stream post, assignment, and People entry.",
                "Focus is visible, controls have meaningful names, and core student tasks work without a mouse.",
            ),
        ],
    },
]


def qn(local: str) -> str:
    return W + local


def ensure_child(parent: etree._Element, local: str) -> etree._Element:
    child = parent.find(qn(local))
    if child is None:
        child = etree.SubElement(parent, qn(local))
    return child


def replace_cell_content(cell: etree._Element, lines, font_pt: float = 9.0, bold: bool = False) -> None:
    if isinstance(lines, str):
        lines = [lines]
    tc_pr = cell.find(qn("tcPr"))
    for child in list(cell):
        if child is not tc_pr:
            cell.remove(child)

    p = etree.SubElement(cell, qn("p"))
    p_pr = etree.SubElement(p, qn("pPr"))
    spacing = etree.SubElement(p_pr, qn("spacing"))
    spacing.set(qn("before"), "0")
    spacing.set(qn("after"), "0")
    spacing.set(qn("line"), "220")
    spacing.set(qn("lineRule"), "auto")

    r = etree.SubElement(p, qn("r"))
    r_pr = etree.SubElement(r, qn("rPr"))
    fonts = etree.SubElement(r_pr, qn("rFonts"))
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(attr), "Arial")
    if bold:
        etree.SubElement(r_pr, qn("b"))
        etree.SubElement(r_pr, qn("bCs"))
    sz = etree.SubElement(r_pr, qn("sz"))
    sz.set(qn("val"), str(int(round(font_pt * 2))))
    sz_cs = etree.SubElement(r_pr, qn("szCs"))
    sz_cs.set(qn("val"), str(int(round(font_pt * 2))))
    color = etree.SubElement(r_pr, qn("color"))
    color.set(qn("val"), "000000")

    if not lines:
        lines = [""]
    for index, line in enumerate(lines):
        if index:
            etree.SubElement(r, qn("br"))
        t = etree.SubElement(r, qn("t"))
        if line.startswith(" ") or line.endswith(" "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = line


def set_metadata(meta: etree._Element, scenario: dict) -> None:
    nested = meta.xpath(".//w:tbl", namespaces=NS)
    if len(nested) != 2:
        raise RuntimeError(f"Expected two nested metadata tables, found {len(nested)}")
    left_rows = nested[0].findall(qn("tr"))
    right_rows = nested[1].findall(qn("tr"))
    left_values = [
        "Google Classroom Student Test Cases",
        scenario["module"],
        "Web app - supported browser - school student account",
        "Student Testing Team",
        "10 September 2026",
        "To be completed",
    ]
    for row, value in zip(left_rows, left_values):
        replace_cell_content(row.findall(qn("tc"))[1], value, font_pt=9.5)
    replace_cell_content(right_rows[0].findall(qn("tc"))[1], scenario["id"], font_pt=9.5, bold=True)
    replace_cell_content(right_rows[1].findall(qn("tc"))[1], scenario["scenario"], font_pt=9.5)


def set_status(cell: etree._Element, unique_id: int) -> None:
    sdt = cell.find(".//w:sdt", namespaces=NS)
    if sdt is None:
        raise RuntimeError("Template status dropdown was not found")
    sdt_pr = sdt.find(qn("sdtPr"))
    id_el = ensure_child(sdt_pr, "id")
    id_el.set(qn("val"), str(unique_id))
    dropdown = sdt_pr.find(qn("dropDownList"))
    if dropdown is not None:
        dropdown.set(qn("lastValue"), "Not Tested")
    text_nodes = sdt.xpath(".//w:sdtContent//w:t", namespaces=NS)
    if not text_nodes:
        raise RuntimeError("Template status dropdown has no display text")
    text_nodes[0].text = "Not Tested"
    for extra in text_nodes[1:]:
        extra.text = ""
    run_pr = sdt.find(".//w:sdtContent/w:r/w:rPr", namespaces=NS)
    if run_pr is not None:
        color = ensure_child(run_pr, "color")
        color.set(qn("val"), "7F6000")
        shd = ensure_child(run_pr, "shd")
        shd.set(qn("val"), "clear")
        shd.set(qn("fill"), "FFF2CC")


def fill_test_table(table: etree._Element, scenario: dict, page_index: int) -> None:
    rows = table.findall(qn("tr"))
    if len(rows) != 6:
        raise RuntimeError(f"Expected six test-table rows, found {len(rows)}")
    cases = scenario["cases"]
    if len(cases) != 5:
        raise RuntimeError("Each scenario must contain exactly five cases")
    for row_index, case in enumerate(cases, start=1):
        cells = rows[row_index].findall(qn("tc"))
        test_case, precondition, procedures, test_data, expected = case
        replace_cell_content(cells[0], test_case)
        replace_cell_content(cells[1], precondition)
        replace_cell_content(cells[2], [f"{i}. {step}" for i, step in enumerate(procedures, start=1)])
        replace_cell_content(cells[3], test_data)
        replace_cell_content(cells[4], expected)
        replace_cell_content(cells[5], "")
        set_status(cells[6], 200_000_000 + page_index * 10 + row_index)


def add_page_break_before(paragraph: etree._Element) -> None:
    p_pr = paragraph.find(qn("pPr"))
    if p_pr is None:
        p_pr = etree.Element(qn("pPr"))
        paragraph.insert(0, p_pr)
    if p_pr.find(qn("pageBreakBefore")) is None:
        etree.SubElement(p_pr, qn("pageBreakBefore"))


def build_document_xml(source_xml: bytes) -> bytes:
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(source_xml, parser)
    body = root.find(qn("body"))
    children = list(body)
    if len(children) < 5:
        raise RuntimeError("Unexpected template body")

    intro_paragraph = children[0]
    meta_template = children[1]
    spacer_template = children[2]
    test_template = children[3]
    section_properties = children[-1]

    for child in list(body):
        body.remove(child)

    for page_index, scenario in enumerate(SCENARIOS):
        intro = copy.deepcopy(intro_paragraph)
        if page_index:
            add_page_break_before(intro)
        meta = copy.deepcopy(meta_template)
        spacer = copy.deepcopy(spacer_template)
        test_table = copy.deepcopy(test_template)
        set_metadata(meta, scenario)
        fill_test_table(test_table, scenario, page_index)
        body.append(intro)
        body.append(meta)
        body.append(spacer)
        body.append(test_table)

    body.append(copy.deepcopy(section_properties))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(REFERENCE, "r") as zin:
        original_document = zin.read("word/document.xml")
        updated_document = build_document_xml(original_document)

        fd, temp_name = tempfile.mkstemp(suffix=".docx", dir=str(OUTPUT.parent))
        os.close(fd)
        try:
            with zipfile.ZipFile(temp_name, "w") as zout:
                for item in zin.infolist():
                    payload = updated_document if item.filename == "word/document.xml" else zin.read(item.filename)
                    zout.writestr(item, payload)
            shutil.move(temp_name, OUTPUT)
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)

    print(f"Created {OUTPUT}")
    print(f"Scenario pages: {len(SCENARIOS)}")
    print(f"Test cases: {sum(len(item['cases']) for item in SCENARIOS)}")


if __name__ == "__main__":
    main()
