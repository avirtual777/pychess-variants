from __future__ import annotations

# -*- coding: utf-8 -*-
from chess import Board, Move, D1, D8, F1, F8, square_file
from fairy import BLACK, WHITE

import logging

log = logging.getLogger(__name__)

try:
    import pyffish as sf
except ImportError:
    log.error("No pyffish module installed!", exc_info=True)


VARIANT = "alice"
CHESS960 = False
COUNT_STARTED = False
START_FEN_0 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
START_FEN_1 = "8/8/8/8/8/8/8/8 w - - 0 1"

CASTLED_ROOK_SQUARE = ((D1, D8), (F1, F8))


class AliceBoard:
    def __init__(self, initial_fen=""):
        self.nnue = False
        self.initial_fen = initial_fen if initial_fen else AliceBoard.start_fen()
        self.move_stack: list[str] = []
        self.castling_move_stack: list[bool] = []
        self.board_id_stack: list[str] = []
        self.ply = 0
        self.fens = self.initial_fen.split(" | ")
        self.boards = (Board(self.fens[0]), Board(self.fens[1]))
        self.color = WHITE if self.fens[0].split()[1] == "w" else BLACK
        self.fen = self.initial_fen
        self.count_started = False

    @staticmethod
    def start_fen():
        return "%s | %s" % (START_FEN_0, START_FEN_1)

    @property
    def alice_fen(self):
        return "%s | %s" % (self.fens[0], self.fens[1])

    def play_move(self, board_id, move):
        castling_move = self.boards[board_id].is_castling(move)

        self.boards[board_id].push(move)

        # Remove piece from the target square and put it to the other board
        # we have to call BaseBoard remove_piece_at() and set_piece_at() methods
        # via super() to avoid clearing the move stack!
        piece = super(Board, self.boards[board_id]).remove_piece_at(move.to_square)
        super(Board, self.boards[1 - board_id]).set_piece_at(move.to_square, piece)

        # Remove the castled rook and put it to the another board
        if castling_move:
            a_side = 0 if square_file(move.to_square) < square_file(move.from_square) else 1
            rook_to_square = CASTLED_ROOK_SQUARE[a_side][self.color]
            rook = super(Board, self.boards[board_id]).remove_piece_at(rook_to_square)
            super(Board, self.boards[1 - board_id]).set_piece_at(rook_to_square, rook)

        # Switch the other board turn color
        self.boards[1 - board_id].turn = not self.boards[1 - board_id].turn

        # Adjust both boards FEN
        self.fens[board_id] = self.boards[board_id].fen()
        self.fens[1 - board_id] = self.boards[1 - board_id].fen()

        return castling_move

    def undo_move(self, board_id, move, castling_move):
        # Remove the castled rook and put it to the original board
        if castling_move:
            a_side = 0 if square_file(move.to_square) < square_file(move.from_square) else 1
            rook_to_square = CASTLED_ROOK_SQUARE[a_side][self.color]
            rook = super(Board, self.boards[1 - board_id]).remove_piece_at(rook_to_square)
            super(Board, self.boards[board_id]).set_piece_at(rook_to_square, rook)

        # Remove piece from the target square and put it to the original board
        piece = super(Board, self.boards[1 - board_id]).remove_piece_at(move.to_square)
        self.boards[1 - board_id].turn = not self.boards[1 - board_id].turn

        super(Board, self.boards[board_id]).set_piece_at(move.to_square, piece)
        self.boards[board_id].pop()

        self.fens[board_id] = self.boards[board_id].fen()
        self.fens[1 - board_id] = self.boards[1 - board_id].fen()

    def push(self, uci, append=True):
        move = Move.from_uci(uci)
        board_id = 0 if self.boards[0].piece_at(move.from_square) else 1
        # print("push()", board_id, uci)
        self.board_id_stack.append(board_id)

        castling_move = self.play_move(board_id, move)

        # self.print_pos()
        if append:
            self.move_stack.append(uci)
            self.castling_move_stack.append(castling_move)
            self.ply += 1
        self.color = 1 - self.color
        self.fen = self.alice_fen

    def pop(self):
        uci = self.move_stack.pop()
        move = Move.from_uci(uci)

        board_id = self.board_id_stack.pop()
        castling_move = self.castling_move_stack.pop()
        # print("pop()", board, uci)

        self.undo_move(board_id, move, castling_move)

        self.ply -= 1
        self.color = 1 - self.color
        # self.print_pos()
        self.fen = self.alice_fen

    def get_san(self, move):
        board_id = 0 if self.boards[0].piece_at(Move.from_uci(move).from_square) else 1
        return sf.get_san(VARIANT, self.fens[board_id], move, CHESS960, sf.NOTATION_SAN)

    def legal_moves(self):
        moves_0 = sf.legal_moves(VARIANT, self.fens[0], [], CHESS960)
        pseudo_legal_moves_0 = [
            uci for uci in moves_0 if self.boards[1].piece_at(Move.from_uci(uci).to_square) is None
        ]

        moves_1 = sf.legal_moves(VARIANT, self.fens[1], [], CHESS960)
        pseudo_legal_moves_1 = [
            uci for uci in moves_1 if self.boards[0].piece_at(Move.from_uci(uci).to_square) is None
        ]

        return self.legal_alice_moves(0, pseudo_legal_moves_0) + self.legal_alice_moves(
            1, pseudo_legal_moves_1
        )

    def switch_fen_moving_color(self, fen):
        old = " %s" % fen[fen.find(" ") + 1]
        new = " w" if old == " b" else " b"
        return fen.replace(old, new)

    def is_invalid_by_checked(self):
        return sf.gives_check(
            VARIANT, self.switch_fen_moving_color(self.fens[0]), [], CHESS960
        ) or sf.gives_check(VARIANT, self.switch_fen_moving_color(self.fens[1]), [], CHESS960)

    def legal_alice_moves(self, board_id, uci_moves):
        legals = []
        for uci in uci_moves:
            move = Move.from_uci(uci)
            castling_move = self.play_move(board_id, move)

            ok = not self.is_invalid_by_checked()

            self.undo_move(board_id, move, castling_move)

            # We have to check that rook_to_square was vacant as well
            if castling_move:
                a_side = 0 if square_file(move.to_square) < square_file(move.from_square) else 1
                rook_to_square = CASTLED_ROOK_SQUARE[a_side][self.color]

                if self.boards[1 - board_id].piece_at(rook_to_square) is not None:
                    ok = False

            if ok:
                legals.append(uci)

        return legals

    def is_checked(self):
        gives_check_0 = sf.gives_check(VARIANT, self.fens[0], [], CHESS960)
        gives_check_1 = sf.gives_check(VARIANT, self.fens[1], [], CHESS960)
        return gives_check_0 or gives_check_1

    def insufficient_material(self):
        return False, False
        # TODO

    def is_immediate_game_end(self):
        return False, None

    def is_optional_game_end(self):
        return False, None
        # TODO

    def is_claimable_draw(self):
        optional_end, result = self.is_optional_game_end()
        return optional_end and result == 0

    def game_result(self):
        cur_color = self.color == WHITE
        board_id = 0 if self.boards[0].king(cur_color) is not None else 1
        return sf.game_result(VARIANT, self.fens[board_id], [], CHESS960)

    def print_pos(self):
        print("================")
        print(self.fens[0])
        print(self.boards[0].unicode(invert_color=True, empty_square="_"))
        print("----------------")
        print(self.fens[1])
        print(self.boards[1].unicode(invert_color=True, empty_square="_"))
