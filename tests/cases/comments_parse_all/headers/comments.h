/*
 * Fixture declarations for parser/renderer comment-copy behavior.
 */

/** Doxygen typedef comment. */
typedef int fixture_doc_type_t;

/* Plain typedef comment. */
typedef int fixture_plain_type_t;

enum fixture_doc_comment_status {
  /// Doxygen enum constant comment.
  FIXTURE_DOC_STATUS = 1,
};

enum fixture_plain_comment_status {
  // Plain enum constant comment.
  FIXTURE_PLAIN_STATUS = 2,
};

/// Doxygen function comment.
int fixture_doc_add(int lhs, int rhs);

// Plain function comment.
int fixture_plain_add(int lhs, int rhs);

/// Doxygen runtime-var comment.
extern int fixture_doc_counter;

// Plain runtime-var comment.
extern int fixture_plain_counter;
