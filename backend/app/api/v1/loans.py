"""Borrowing and returning endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.enums import LoanStatus
from app.core.security import Actor, get_current_actor
from app.schemas.loan import BorrowRequest, LoanListResponse, LoanOut, ReturnPreview
from app.services import loan_service


router = APIRouter(prefix="/loans", tags=["loans"])
ActorDependency = Annotated[Actor, Depends(get_current_actor)]


@router.get("", response_model=LoanListResponse)
def list_loan_records(
    actor: ActorDependency,
    loan_no: str | None = None,
    student_id: str | None = None,
    status: LoanStatus | None = None,
    overdue: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LoanListResponse:
    return loan_service.list_loans(
        actor,
        loan_no=loan_no,
        student_id=student_id,
        status=status,
        overdue=overdue,
        page=page,
        page_size=page_size,
    )


@router.post("/borrow", response_model=LoanOut, status_code=201)
def borrow_book(request: BorrowRequest, actor: ActorDependency) -> LoanOut:
    return loan_service.borrow_book(
        actor,
        book_id=request.book_id,
        isbn=request.isbn,
        book_code=request.book_code,
        reader_id=request.reader_id,
    )


@router.get("/{loan_id}", response_model=LoanOut)
def get_loan_record(loan_id: int, actor: ActorDependency) -> LoanOut:
    return loan_service.get_loan(actor, loan_id)


@router.get("/{loan_id}/receipt", response_model=LoanOut)
def get_loan_receipt(loan_id: int, actor: ActorDependency) -> LoanOut:
    return loan_service.get_loan(actor, loan_id)


@router.get("/{loan_id}/return-preview", response_model=ReturnPreview)
def return_preview(loan_id: int, actor: ActorDependency) -> ReturnPreview:
    return loan_service.get_return_preview(actor, loan_id)


@router.post("/{loan_id}/return", response_model=LoanOut)
def return_book(loan_id: int, actor: ActorDependency) -> LoanOut:
    return loan_service.return_book(actor, loan_id)


@router.post("/{loan_id}/fine/pay", response_model=LoanOut)
def pay_fine(loan_id: int, actor: ActorDependency) -> LoanOut:
    return loan_service.mark_fine_paid(actor, loan_id)
