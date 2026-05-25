from __future__ import annotations

import unittest

from backend.record_planner import example_operations, select_record_candidates


def candidate(table: int, row: int, cell: int, text: str = "", left: str = "", right: str = "", rows: list[str] | None = None) -> dict:
    return {
        "locator": f"table[{table}].row[{row}].cell[{cell}]",
        "table": table,
        "row": row,
        "cell": cell,
        "span_start": cell,
        "span_end": cell,
        "text": text,
        "left_text": left,
        "right_text": right,
        "row_texts": rows or [],
    }


def layout(input_candidates: list[dict], tables: list[dict]) -> dict:
    return {"input_candidates": input_candidates, "tables": tables, "summary": {}}


class RecordPlannerTest(unittest.TestCase):
    def test_education_second_record_uses_second_input_row_and_column_headers(self) -> None:
        rows = [
            {
                "row": 0,
                "cells": [
                    {"cell": 0, "span_start": 0, "span_end": 0, "text": "학 력 사 항"},
                    {"cell": 1, "span_start": 1, "span_end": 1, "text": "구 분"},
                    {"cell": 2, "span_start": 2, "span_end": 2, "text": "입학년월"},
                    {"cell": 3, "span_start": 3, "span_end": 3, "text": "졸업년월"},
                    {"cell": 4, "span_start": 4, "span_end": 4, "text": "학교명"},
                    {"cell": 5, "span_start": 5, "span_end": 5, "text": "전공"},
                ],
            }
        ]
        input_candidates = [
            candidate(1, 1, 2, left="고등학교", rows=["학 력 사 항", "고등학교", "", "", "", ""]),
            candidate(1, 1, 4, left="고등학교", rows=["학 력 사 항", "고등학교", "", "", "", ""]),
            candidate(1, 1, 5, left="고등학교", rows=["학 력 사 항", "고등학교", "", "", "", ""]),
            candidate(1, 2, 2, left="대학교", rows=["학 력 사 항", "대학교", "", "", "", ""]),
            candidate(1, 2, 4, left="대학교", rows=["학 력 사 항", "대학교", "", "", "", ""]),
            candidate(1, 2, 5, left="대학교", rows=["학 력 사 항", "대학교", "", "", "", ""]),
        ]
        fields = [
            {"field": "education[1].period", "value": "2009-03 ~ 2015-02"},
            {"field": "education[1].school", "value": "일육대학교"},
            {"field": "education[1].major", "value": "컴퓨터공학과"},
        ]

        selected = select_record_candidates(layout(input_candidates, [{"table": 0, "rows": []}, {"table": 1, "rows": rows}]), "education[1]", fields, [], set())
        operations = example_operations(fields, selected)

        self.assertEqual([op["target"]["row"] for op in operations], [2, 2, 2])
        self.assertEqual([op["target"]["cell"] for op in operations], [2, 4, 5])

    def test_certificate_records_skip_header_row(self) -> None:
        rows = [
            {
                "row": 0,
                "cells": [
                    {"cell": 0, "span_start": 0, "span_end": 0, "text": "자격 사 항"},
                    {"cell": 1, "span_start": 1, "span_end": 1, "text": "특수자격및면허"},
                    {"cell": 2, "span_start": 2, "span_end": 2, "text": "등급"},
                    {"cell": 3, "span_start": 3, "span_end": 3, "text": "취득일"},
                ],
            }
        ]
        input_candidates = [
            candidate(3, 0, 3, left="등급", right="어 학 사 항", rows=["자격 사 항", "특수자격및면허", "등급", ""]),
            candidate(3, 1, 1, left="자격 사 항", right="어 학 사 항", rows=["자격 사 항", "", "", ""]),
            candidate(3, 1, 2, left="자격 사 항", right="어 학 사 항", rows=["자격 사 항", "", "", ""]),
            candidate(3, 1, 3, left="자격 사 항", right="어 학 사 항", rows=["자격 사 항", "", "", ""]),
        ]
        fields = [
            {"field": "certificates[0].name", "value": "정보처리기사"},
            {"field": "certificates[0].issuer", "value": "한국산업인력공단"},
            {"field": "certificates[0].date", "value": "2023.06"},
        ]

        selected = select_record_candidates(
            layout(input_candidates, [{"table": 0, "rows": []}, {"table": 1, "rows": []}, {"table": 2, "rows": []}, {"table": 3, "rows": rows}]),
            "certificates[0]",
            fields,
            [],
            set(),
        )

        self.assertTrue(selected)
        self.assertEqual({item["row"] for item in selected}, {1})

    def test_language_value_visible_as_row_label_is_not_duplicated(self) -> None:
        input_candidates = [
            candidate(3, 0, 6, left="영어", right="특 기 사 항", rows=["어 학 사 항", "영어", "", ""]),
            candidate(3, 0, 7, left="영어", right="특 기 사 항", rows=["어 학 사 항", "영어", "", ""]),
        ]
        fields = [
            {"field": "languages[0].language", "value": "영어"},
            {"field": "languages[0].ability", "value": "상"},
            {"field": "languages[0].test", "value": "TOEIC"},
            {"field": "languages[0].score", "value": "900"},
        ]

        selected = select_record_candidates(layout(input_candidates, [{"table": 3, "rows": []}]), "languages[0]", fields, [], set())
        operations = example_operations(fields, selected)

        self.assertNotIn("languages[0].language", {op["field"] for op in operations})

    def test_language_section_ignores_adjacent_computer_cells(self) -> None:
        rows = [
            {
                "row": 0,
                "cells": [
                    {"cell": 0, "span_start": 0, "span_end": 0, "text": "외국어"},
                    {"cell": 2, "span_start": 2, "span_end": 2, "text": "외국어명"},
                    {"cell": 3, "span_start": 3, "span_end": 3, "text": "활용능력"},
                    {"cell": 5, "span_start": 5, "span_end": 5, "text": "테스트명"},
                    {"cell": 10, "span_start": 10, "span_end": 10, "text": "공인점수"},
                    {"cell": 14, "span_start": 14, "span_end": 14, "text": "컴퓨터"},
                    {"cell": 16, "span_start": 16, "span_end": 16, "text": "MS-WORD"},
                    {"cell": 17, "span_start": 17, "span_end": 17, "text": "상"},
                ],
            }
        ]
        input_candidates = [
            candidate(0, 20, 17, text="상( ) 중( ) 하( )", left="MS-WORD", rows=["외국어", "외국어명", "활용능력", "테스트명", "공인점수", "컴퓨터", "MS-WORD", "상"]),
            candidate(0, 21, 2, left="외국어", right="컴퓨터", rows=["외국어", "", "", "", "", "컴퓨터", "MS-EXCEL", "상( ) 중( ) 하( )"]),
            candidate(0, 21, 3, left="외국어", right="컴퓨터", rows=["외국어", "", "", "", "", "컴퓨터", "MS-EXCEL", "상( ) 중( ) 하( )"]),
            candidate(0, 21, 5, left="외국어", right="컴퓨터", rows=["외국어", "", "", "", "", "컴퓨터", "MS-EXCEL", "상( ) 중( ) 하( )"]),
            candidate(0, 21, 10, left="외국어", right="컴퓨터", rows=["외국어", "", "", "", "", "컴퓨터", "MS-EXCEL", "상( ) 중( ) 하( )"]),
            candidate(0, 21, 17, text="상( ) 중( ) 하( )", left="MS-EXCEL", rows=["외국어", "", "", "", "", "컴퓨터", "MS-EXCEL", "상( ) 중( ) 하( )"]),
        ]
        fields = [
            {"field": "languages[0].language", "value": "영어"},
            {"field": "languages[0].ability", "value": "상"},
            {"field": "languages[0].test", "value": "TOEIC"},
            {"field": "languages[0].score", "value": "900"},
        ]

        selected = select_record_candidates(layout(input_candidates, [{"table": 0, "rows": rows}]), "languages[0]", fields, [], set())
        operations = example_operations(fields, selected)

        self.assertEqual([op["target"]["row"] for op in operations], [21, 21, 21, 21])
        self.assertEqual([op["target"]["cell"] for op in operations], [2, 3, 5, 10])

    def test_military_record_uses_military_columns(self) -> None:
        rows = [
            {
                "row": 0,
                "cells": [
                    {"cell": 0, "span_start": 0, "span_end": 0, "text": "병 역"},
                    {"cell": 1, "span_start": 1, "span_end": 1, "text": "구 분"},
                    {"cell": 2, "span_start": 2, "span_end": 2, "text": "군별"},
                    {"cell": 3, "span_start": 3, "span_end": 3, "text": "역종"},
                    {"cell": 4, "span_start": 4, "span_end": 4, "text": "계급"},
                    {"cell": 5, "span_start": 5, "span_end": 5, "text": "복무기간"},
                    {"cell": 6, "span_start": 6, "span_end": 6, "text": "면제사유"},
                ],
            }
        ]
        input_candidates = [
            candidate(2, 1, 1, left="병 역", rows=["병 역", "", "", "", "", "", ""]),
            candidate(2, 1, 2, left="병 역", rows=["병 역", "", "", "", "", "", ""]),
            candidate(2, 1, 3, left="병 역", rows=["병 역", "", "", "", "", "", ""]),
            candidate(2, 1, 4, left="병 역", rows=["병 역", "", "", "", "", "", ""]),
            candidate(2, 1, 5, left="병 역", rows=["병 역", "", "", "", "", "", ""]),
            candidate(2, 1, 6, left="병 역", rows=["병 역", "", "", "", "", "", ""]),
        ]
        fields = [
            {"field": "military[0].status", "value": "군필"},
            {"field": "military[0].branch", "value": "육군"},
            {"field": "military[0].service_type", "value": "현역"},
            {"field": "military[0].rank", "value": "병장"},
            {"field": "military[0].period", "value": "2010-03 ~ 2012-01"},
        ]

        selected = select_record_candidates(
            layout(input_candidates, [{"table": 0, "rows": []}, {"table": 1, "rows": []}, {"table": 2, "rows": rows}]),
            "military[0]",
            fields,
            [],
            set(),
        )
        operations = example_operations(fields, selected)

        self.assertEqual([op["target"]["cell"] for op in operations], [1, 2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main()
