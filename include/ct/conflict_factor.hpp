#ifndef LIBCT_CONFLICT_FACTOR_HPP
#define LIBCT_CONFLICT_FACTOR_HPP

namespace ct {

class conflict_primal {
public:
  static constexpr index undecided = std::numeric_limits<index>::max();

  conflict_primal()
  : index_(undecided)
  { }

  void reset() { index_ = undecided; }

  void set(index i)
  {
    assert(index_ == undecided || index_ == i);
    index_ = i;
  }

  index get() const { return index_; }

  bool is_undecided() const { return index_ == undecided; }
  bool is_set() const { return index_ != undecided; }

protected:
  index index_;
};


template<typename ALLOCATOR = std::allocator<cost>>
class conflict_factor {
public:
  using allocator_type = ALLOCATOR;
  static constexpr cost initial_cost = 0.0;

  conflict_factor(index number_of_detections, const ALLOCATOR& allocator = ALLOCATOR())
  : costs_(number_of_detections + 1, initial_cost, allocator)
#ifndef NDEBUG
  , timestep_(-1)
  , index_(-1)
#endif
  {
  }

  conflict_factor(const conflict_factor& other) = delete;
  conflict_factor& operator=(const conflict_factor& other) = delete;

#ifndef NDEBUG
  void set_debug_info(index timestep, index idx)
  {
    timestep_ = timestep;
    index_ = idx;
  }

  std::string dbg_info() const
  {
    std::ostringstream s;
    s << "c(" << timestep_ << ", " << index_ << ")";
    return s.str();
  }
#endif

  auto size() const { return costs_.size(); }

  bool is_prepared() const { return true; }

  void set(const index idx, cost c) { assert_index(idx); costs_[idx] = c; }
  cost get(const index idx) { assert_index(idx); return costs_[idx]; }

  cost lower_bound() const
  {
    assert(costs_.size() > 0);
    return *std::min_element(costs_.begin(), costs_.end());
  }

  void repam(const index idx, const cost msg)
  {
    assert_index(idx);
    costs_[idx] += msg;
  }

  void reset_primal() { primal_.reset(); }

  cost evaluate_primal() const
  {
    if (primal_.is_set())
      return costs_[primal_.get()];
    else
      return std::numeric_limits<cost>::infinity();
  }

  auto& primal() { return primal_; }
  const auto& primal() const { return primal_; }

  void round_primal()
  {
    if (primal_.is_undecided()) {
      auto min = std::min_element(costs_.cbegin(), costs_.cend());
      primal_.set(min - costs_.cbegin());
    }
  }

protected:
  void assert_index(const index idx) const { assert(idx >= 0 && idx < costs_.size() - 1); }

  fixed_vector_alloc_gen<cost, ALLOCATOR> costs_;
  conflict_primal primal_;

#ifndef NDEBUG
  index timestep_, index_;
#endif

  friend struct transition_messages;
  friend struct conflict_messages;
  template<typename> friend class gurobi_conflict_factor;
};

}

#endif

/* vim: set ts=8 sts=2 sw=2 et ft=cpp: */
