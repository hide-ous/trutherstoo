# adapted from from https://gist.github.com/zhicongchen/9e23d5c3f1e5b1293b16133485cd17d8
# adn https://github.com/williamleif/histwords/blob/master/vecanalysis/seq_procrustes.py
import copy
import os

import gensim
import numpy as np
from gensim import downloader
from gensim.models import Word2Vec
from collections import OrderedDict


def load_embeddings(dirpath='../../models/embeddings/'):
    to_return = OrderedDict()
    for year_str in os.listdir(dirpath):
        if not year_str.endswith('.model'): continue
        year = int(year_str[-10:-6])
        to_return[year] = Word2Vec.load(
            os.path.join(dirpath,
                         f"word2vec_{year}.model"))
    return to_return


def smart_procrustes_align_gensim(base_embed, other_embed, words=None):
    """
    Original script: https://gist.github.com/quadrismegistus/09a93e219a6ffc4f216fb85235535faf
    Procrustes align two gensim word2vec models (to allow for comparison between same word across models).
    Code ported from HistWords <https://github.com/williamleif/histwords> by William Hamilton <wleif@stanford.edu>.

    First, intersect the vocabularies (see `intersection_align_gensim` documentation).
    Then do the alignment on the other_embed model.
    Replace the other_embed model's syn0 and syn0norm numpy matrices with the aligned version.
    Return other_embed.

    If `words` is set, intersect the two models' vocabulary with the vocabulary in words (see `intersection_align_gensim` documentation).
    """

    # patch by Richard So [https://twitter.com/richardjeanso) (thanks!) to update this code for new version of gensim
    # base_embed.init_sims(replace=True)
    # other_embed.init_sims(replace=True)

    # make sure vocabulary and indices are aligned
    in_base_embed, in_other_embed = intersection_align_gensim(base_embed,
                                                              other_embed,
                                                              words=words)

    # get the (normalized) embedding matrices
    in_base_embed.wv.fill_norms(force=True)
    in_other_embed.wv.fill_norms(force=True)
    base_vecs = in_base_embed.wv.get_normed_vectors()
    other_vecs = in_other_embed.wv.get_normed_vectors()

    # just a matrix dot product with numpy
    m = other_vecs.T.dot(base_vecs)
    # SVD method from numpy
    u, _, v = np.linalg.svd(m)
    # another matrix operation
    ortho = u.dot(v)
    # Replace original array with modified one, i.e. multiplying the embedding matrix by "ortho"

    other_embed_copy = copy.deepcopy(in_other_embed)
    other_embed_copy.wv.vectors = (in_other_embed.wv.vectors).dot(ortho)
    return other_embed_copy


def intersection_align_gensim(m1, m2, words=None):
    """
    Intersect two gensim word2vec models, m1 and m2.
    Only the shared vocabulary between them is kept.
    If 'words' is set (as list or set), then the vocabulary is intersected with this list as well.
    Indices are re-organized from 0..N in order of descending frequency (=sum of counts from both m1 and m2).
    These indices correspond to the new syn0 and syn0norm objects in both gensim models:
        -- so that Row 0 of m1.syn0 will be for the same word as Row 0 of m2.syn0
        -- you can find the index of any word on the .index2word list: model.index2word.index(word) => 2
    The .vocab dictionary is also updated for each model, preserving the count but updating the index.
    """

    # Get the vocab for each model
    vocab_m1 = set(m1.wv.index_to_key)
    vocab_m2 = set(m2.wv.index_to_key)

    # Find the common vocabulary
    common_vocab = vocab_m1 & vocab_m2
    if words: common_vocab &= set(words)

    # If no alignment necessary because vocab is identical...
    if not vocab_m1 - common_vocab and not vocab_m2 - common_vocab:
        return (m1, m2)

    # Otherwise sort by frequency (summed for both)
    common_vocab = list(common_vocab)
    common_vocab.sort(
        key=lambda w: m1.wv.get_vecattr(w, "count") + m2.wv.get_vecattr(w,
                                                                        "count"),
        reverse=True)
    print(len(common_vocab))

    # Then for each model...
    for m in [m1, m2]:
        # Replace old syn0norm array with new one (with common vocab)
        indices = [m.wv.key_to_index[w] for w in common_vocab]
        old_arr = m.wv.vectors
        new_arr = np.array([old_arr[index] for index in indices])
        m.wv.vectors = new_arr

        # Replace old vocab dictionary with new one (with common vocab)
        # and old index2word with new one
        new_key_to_index = {}
        new_index_to_key = []
        for new_index, key in enumerate(common_vocab):
            new_key_to_index[key] = new_index
            new_index_to_key.append(key)
        m.wv.key_to_index = new_key_to_index
        m.wv.index_to_key = new_index_to_key

        print(len(m.wv.key_to_index), len(m.wv.vectors))

    return (m1, m2)


def align_years(in_dir, out_dir='../../models/embeddings/', max_year=2022, min_year=2012):
    first_iter = True
    base_embed = None
    years_and_embeddings = load_embeddings(in_dir)
    for year, year_embed in ((k, years_and_embeddings[k]) for k in reversed(years_and_embeddings)):
        print("Aligning year:", year)
        if year > max_year: continue
        elif year < min_year: break
        if first_iter:
            aligned_embed = year_embed
            first_iter = False
        else:
            aligned_embed = smart_procrustes_align_gensim(base_embed,
                                                          year_embed)
        base_embed = aligned_embed
        print("Writing year:", year)
        os.makedirs(out_dir, exist_ok=True)
        aligned_embed.save(
            os.path.join(out_dir,
                         f"word2vec_{year}.model"))


if __name__ == '__main__':

    import gensim.downloader as api
    from gensim.models.word2vec import Word2Vec
    from collections import defaultdict, OrderedDict

    c1 = api.load('text8')
    c2_ = api.load('20-newsgroups')

    stoplist = set('for a of the and to in'.split())
    texts = [
        [word for word in document.lower().split() if word not in stoplist]
        for document in c2_
    ]

    # remove words that appear only once
    frequency = defaultdict(int)
    for text in texts:
        for token in text:
            frequency[token] += 1

    c2 = [
        [token for token in text if frequency[token] > 1]
        for text in texts
    ]

    m1 = Word2Vec(c1)
    m2 = Word2Vec(c2)
    smart_procrustes_align_gensim(m1, m2)
