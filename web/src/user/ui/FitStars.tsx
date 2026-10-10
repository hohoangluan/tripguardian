// Five stars filled by the fraction: how well a place fits this trip's wishes (Card.fit), not how good the place is.
const STAR = 'M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3 6.1 20.6l1.3-6.6L2.5 9.4l6.6-.8z'

const Star = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path d={STAR} fill="currentColor" /></svg>

export function FitStars({ stars }: { stars: number }) {
  return (
    <span className="tg-stars" role="img" aria-label={`Hợp với bạn ${stars.toFixed(1)} trên 5 sao`}>
      {[0, 1, 2, 3, 4].map((i) => (
        <i key={i} className="tg-star"><Star /><b style={{ width: `${Math.max(0, Math.min(1, stars - i)) * 100}%` }}><Star /></b></i>
      ))}
    </span>
  )
}
