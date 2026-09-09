export function chapterReviewScore(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null;
  const score = Number(value);
  return Number.isFinite(score) && score >= 0 && score <= 10 ? score : null;
}

export function chapterReviewMap(reviews) {
  return new Map(reviews.map(item => [item.chapter_id, chapterReviewScore(item.score)]));
}
