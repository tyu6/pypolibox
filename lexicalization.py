#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Arne Neumann <arne-neumann@web.de>

"""
This module shall convert C{TextPlan}s into HLDS XML structures which can
be utilized by the OpenCCG surface realizer to produce natural language text.

TODO: move OPENCCG_BIN_PATH and GRAMMAR_PATH to a config.yml file and make them
absolute
"""

import os
import re
import random
from copy import deepcopy
from tempfile import NamedTemporaryFile
from commands import getstatusoutput
from nltk.featstruct import Feature
from textplan import ConstituentSet, Message
from hlds import (Diamond, Sentence, create_hlds_testbed, diamond2sentence, 
                  last_diamond_index, add_nom_prefixes, add_mode_suffix, 
                  remove_nom_prefixes)
from util import ensure_unicode, write_to_file, sql_array_to_set #TODO: dbg, rm
from database import get_column #TODO: dbg, rm

OPENCCG_BIN_PATH = "/home/guido/bin/openccg/bin"
GRAMMAR_PATH = "openccg-jpolibox"


def test_keywords():
    """
    retrieves all sets of keywords from the database and realizes them with
    I{ccg-realize}.
    """
    keyword_arrays = get_column("keywords")
    for keyword_array in keyword_arrays:
        keyword_list = list(sql_array_to_set(keyword_array))
        lexicalized_keywords = lexicalize_keywords(keyword_list, 
                                                   realize="complete")
        print keyword_list, "\n", realize(lexicalized_keywords), "\n\n"

def test_authors():
    """
    retrieves all sets of authors from the database and realizes them with 
    I{ccg-realize}.
    """
    author_arrays = get_column("authors")
    for author_array in author_arrays:
        author_list = list(sql_array_to_set(author_array))
        lexicalized_authors = lexicalize_authors(author_list, 
                                                 realize="complete")
        print author_list, "\n", realize(lexicalized_authors), "\n\n"


def test_titles():
    """
    retrieves all book titles and realizes 10 random combinations of these with
    I{ccg-realize}.
    """
    all_titles = get_column("title")
    num_of_books = lambda : random.randint(1,4)
    book_titles = lambda : random.sample(all_titles, num_of_books())
    
    for i in xrange(10):
        temp_titles = book_titles()
        print "\n\n", temp_titles
        realized_titles = realize(lexicalize_titles(temp_titles, 
                                                    realize="complete"))
        for title in realized_titles:
            print title
        
                                                   

def realize(sentence, results="all"):
    """
    realizes a sentence by calling OpenCCG's I{ccg-realize} binary.

    TODO: check if 'Best Joined Edges' do play a significant role (they're not
    always present)

    @type sentence: C{str} or C{Diamond} or C{Sentence}
    @param sentence:
     - a string: the path to an HLDS XML sentence file (absolute path or
       relative to GRAMMAR_PATH)
     - a Diamond instance
     - a Sentence instance

    @type results: C{str}
    @param results:
    - "debug": return the raw results from ccg-realize
    - "all": return all strings that ccg-realize could produce ("Complete
      Edges")
    - "best": return only the best result from ccg-realize ("Best Edge")

    @rtype: C{str} or C{list} of C{str}
    @return: a string (the "best" result from OpenCCG) OR a list of string,
    containing "all" results that could be realized by OpenCCG
    """
    current_dir = os.getcwd()
    os.chdir(GRAMMAR_PATH)
    grammar_abspath = os.getcwd()
    realizer = os.path.join(OPENCCG_BIN_PATH, "ccg-realize")

    if type(sentence) is str: # realize a file
        file_path = os.path.join(grammar_abspath, sentence)
        if os.path.isfile(file_path):
            status, output = getstatusoutput("{0} {1}".format(realizer,
                                                              file_path))
            with open(file_path, "r") as f:
                sent_xml_str = f.read() # used for results="debug"

            os.chdir(current_dir)
        else:
            os.chdir(current_dir)
            raise Exception, "{0} is not a file.\n" \
                "Please use an absolute path or one that is relative to:\n" \
                "{1}".format(file_path, grammar_abspath)

    elif type(sentence) is Diamond or type(sentence) is Sentence:
        if type(sentence) is Diamond:
            sentence = diamond2sentence(sentence)

        sent_xml_str = create_hlds_testbed(sentence, mode="realize",
                                           output="xml")

        tmp_file = NamedTemporaryFile(mode="w", delete=False)
        tmp_file.write(sent_xml_str)
        tmp_file.close()

        status, output = getstatusoutput("{0} {1}".format(realizer,
                                                          tmp_file.name))
        os.chdir(current_dir)

    else:
        os.chdir(current_dir)
        raise Exception, "Sorry, I can only realize HLDS XML sentence files," \
            " Sentence and Diamond instances."

    if status != 0:
        raise Exception, "Error: Can't run ccg-realize properly." \
            "Error message is:\n\n{0}".format(output)
    else:
        if results == "debug":
            input_and_output = \
                "Input:\n{0}\n\n\nOutput:\n{1}".format(sent_xml_str, output)
            return input_and_output

        res = re.compile("Complete Edges \(sorted\):\n")
        complete_vs_best = re.compile("\nBest Edge:\n")
        sentence_header = re.compile("\{.*?\} \[.*?\] ")
        sentence_tail = re.compile(" :- ")

        _, results_str = res.split(output)
        complete_edges_str, best_edge = complete_vs_best.split(results_str)

        if not complete_edges_str: #if there are no complete edges
            best_vs_best_joined = re.compile("\nBest Joined Edge:\n")
            best_edge, best_joined = best_vs_best_joined.split(best_edge)

        if results == "best":
            _, best_edge_and_tail = sentence_header.split(best_edge)
            best_result, _ = sentence_tail.split(best_edge_and_tail)
            return best_result

        elif results == "all":
            if complete_edges_str:
                complete_edges_list = complete_edges_str.splitlines()
                result_edges = []
                for complete_edge in complete_edges_list:
                    # maxsplit=1 is needed if there are 'Best Joined Edges'
                    _, edge_and_tail = sentence_header.split(complete_edge,
                                                             maxsplit=1)
                    edge, _ = sentence_tail.split(edge_and_tail, maxsplit=1)
                    result_edges.append(edge)
                return list(set(result_edges)) # remove duplicates, return a list
            else: # if there are no complete edges
                _, best_edge_and_tail = sentence_header.split(best_edge)
                best_edge_result, _ = sentence_tail.split(best_edge_and_tail)
                _, best_joined_and_tail = sentence_header.split(best_joined)
                best_joined_result, _ = sentence_tail.split(best_joined_and_tail)
                return [best_edge_result, best_joined_result]


def linearize_textplan(textplan): #TODO: add better explanation to docstring
    """
    takes a text plan (RST tree) and returns an ordered list of constituent
    sets (RST relations that combine two messages).

    @type textplan: C{TextPlan}
    @param textplan: a complete text plan (RST tree) encoded as a feature
    structure

    @rtype: C{list} of C{ConstituentSet}s
    @return: a list of constituent sets in the order they should be realized by
    surface generation
    """
    rstree = textplan["children"] # we don't need to process the title/metadata
    if type(rstree) is Message:
        # if the text plan just consists of one message, return it
        return rstree

    start = 0
    rst_list = __rstree2list(rstree)
    #~ if not rst_list:
        #~ return []

    for i in range(len(rst_list)-1):
    # we're looking for the first element of the list that is the nucleus of
    # its successor.
        if rst_list[i] is not rst_list[i+1][Feature("nucleus")]:
            pass
        else:
            start = i
            break

    linearized_structures = []
    linearized_structures.append(rst_list[start])

    rest = rst_list[start+1:]
    # if rst_list contains only one element, this loop won't be executed at all
    for i, fs in enumerate(rest):
        if type(fs[Feature("satellite")]) is Message:
            structure = ConstituentSet(relType=fs[Feature("relType")],
                                       satellite=fs[Feature("satellite")])
            linearized_structures.append(structure)

        elif type(fs[Feature("satellite")]) is ConstituentSet:
        # if the satellite is nested further
            structure = ConstituentSet(relType=fs[Feature("relType")])
            linearized_structures.append(structure)

            nested_structure = fs[Feature("satellite")]
            linearized_structures.append(nested_structure)
    return linearized_structures

def __rstree2list(featstruct):
    rst_list = [fs for fs in featstruct.walk() if type(fs) is ConstituentSet]
    rst_list.reverse()
    return rst_list


def lexicalize_titles(book_titles, authors=None, realize="abstract"):
    """
    @type book_title: C{list} of C{str}
    @param book_title: list of book title strings
    
    @type authors: C{list} of C{str} OR C{NoneType}
    @param authors: an I{optional} list of author names
    
    @type realize: C{str}
    @param realize: "abstract", "complete". 
    - "abstract" realizes 'das Buch' / 'die Bücher'
    - "pronoun" realizes 'es' / 'sie'
    - "complete" realizes book titles in the format specified in the 
      OpenCC grammar, e.g. „ Computational Linguistics. An Introduction “
    - "authors+title" realizes ONE book title and its authors, e.g. Noam 
      Chomskys „ Syntax “ OR „ Syntax “ von Noam Chomsky
    """
    assert isinstance(book_titles, list), "needs a list of titles as input"
    num_of_titles = len(book_titles)
    
    if realize == "abstract":
        return gen_abstract_title(num_of_titles)

    elif realize == "pronoun":
        return gen_personal_pronoun(num_of_titles, "neut", 3)

    elif realize == "complete":            
        realized_titles = []
        for title in book_titles:
            realized_titles.append(gen_title(title))
        titles_enum = __gen_enumeration(realized_titles, mode="NP")
        add_nom_prefixes(titles_enum)
        add_mode_suffix(titles_enum, mode="NP")
        return titles_enum

    elif realize == "authors+title":
        assert authors and isinstance(authors, list), \
            "authors+title mode needs a non-empty list of authors as input"
        assert num_of_titles == 1, \
            "authors+title mode can only realize one book title"
        title_diamond = gen_title(book_titles[0])
        authors_diamond = lexicalize_authors(authors, realize="complete")
        
        authors_diamond.update({Feature("mode"): "ASS"})
        
        return title_diamond, authors_diamond


def gen_title(book_title):
    """
    Converts a book title (string) into its corresponding HLDS diamond
    structure. Since book titles are hard coded into the grammar, the OpenCCG
    output will differ somewhat, e.g.::

        'Computational Linguistics' --> '„ Computational Linguistics “'

    @type book_title: C{unicode}
    @rtype: C{Diamond}
    """
    book_title = ensure_unicode(book_title)
    book_title = book_title.replace(u" ", u"_")

    opening_bracket = Diamond()
    opening_bracket.create_diamond('99', u'anf\xfchrung\xf6ffnen',
                                   u'anf\xf6ffn', [])
    closing_bracket = Diamond()
    closing_bracket.create_diamond('66', u'anf\xfchrungschlie\xdfen',
                                   'anfschl', [])

    title_diamond = Diamond()
    title_diamond.create_diamond('NP', 'buchtitel', book_title,
                                 [opening_bracket, closing_bracket])
    return title_diamond


def gen_abstract_title(number_of_books):
    """
    given an integer representing a number of books returns a Diamond, which
    can be realized as either "das Buch" or "die Bücher"

    @type number_of_books: C{int}
    @rtype: C{Diamond}
    """
    if number_of_books is 1:
        num_str = "sing"
    if number_of_books > 1:
        num_str = "plur"

    num = Diamond()
    num.create_diamond("NUM", "", num_str, [])
    
    art = Diamond()
    art.create_diamond("ART", "sem-obj", "def", [])

    title = Diamond()
    title.create_diamond("", "artefaktum", "Buch", [num, art])
    return title


def lexicalize_authors(authors, realize="abstract"):
    """
    converts a list of authors into several possible HLDS diamond
    structures, which can be used for text generation.

    @type name: C{list} of C{str}
    @param name: list of names, e.g. ["Ronald Hausser", 
    "Christopher D. Manning"]
    
    @type realize: C{str}
    @param realize: "abstract", "lastnames", "complete". 
    "abstract" realizes 'das Buch' / 'die Bücher'. "lastnames" realizes 
    only the last names of authors, while "complete" realizes their given 
    and last names.

    @rtype: C{list} of C{Diamond}s
    @return: a list of 3 Diamond instance. the first generates "der Autor", the
    second the authors lastnames and the last one generates the complete names 
    of the authors.
    """
    assert isinstance(authors, list), "needs a list of name strings as input"
    num_of_authors = len(authors)
    
    abstract_authors = __gen_abstract_autor(num_of_authors)

    lastnames = []
    complete_names = []
    for author in authors:
        lastnames.append(__gen_lastname_only(author))
        complete_names.append(__gen_complete_name(author))
        
    lastnames_enum = __gen_enumeration(lastnames, mode="NP")
    complete_names_enum = __gen_enumeration(complete_names, mode="NP")

    for realisation in (abstract_authors, lastnames_enum, complete_names_enum):
        add_nom_prefixes(realisation)
        add_mode_suffix(realisation, mode="NP")
        add_mode_suffix(realisation, mode="N")
    
    assert realize in ("abstract", "lastnames", "complete"), \
        "choose 1 of these author realizations: abstract, lastnames, complete"
    
    if realize == "abstract":
        return abstract_authors
    elif realize == "lastnames":
        return lastnames_enum
    elif realize == "complete":
        return complete_names_enum


def __gen_abstract_autor(num_of_authors):
    """
    given an integer (number of authors), returns a Diamond instance which
    generates "der Autor" or "die Autoren".

    @type num_of_authors: C{int}
    @param num_of_authors: the number of authors of a book

    @rtype: C{Diamond}
    """
    if num_of_authors == 1:
        num_str = "sing"
    elif num_of_authors > 1:
        num_str = "plur"

    art = Diamond()
    art.create_diamond("ART", "sem-obj", "def", [])
    gen = Diamond()
    gen.create_diamond("GEN", "", "mask", [])
    num = Diamond()
    num.create_diamond("NUM", "", num_str, [])

    der_autor = Diamond()
    der_autor.create_diamond("", u"bel-phys-körper", "Autor",
                            [art, gen, num])
    return der_autor


def __gen_lastname_only(name):
    """
    given an authors name ("Christopher D. Manning"), the function returns a
    Diamond instance which can be used to realize the author's last name.

    NOTE: This does not work with last names that include whitespace, e.g.
    "du Bois" or "von Neumann".

    @type name: C{str}
    @rtype: C{Diamond}
    """
    _, lastname_str = __split_name(name)
    lastname_only = Diamond()
    lastname = Diamond()
    lastname.create_diamond("NP", "nachname", lastname_str, [])
    return lastname


def __gen_complete_name(name):
    """
    takes a name as a string and returns a corresponding nested HLDS diamond
    structure.

    @type name: C{str}
    @rtype: C{Diamond}
    """
    given_names, lastname_str = __split_name(name)
    complete_name = Diamond()
    if given_names:
        given_names_diamond = __create_nested_given_names(given_names)
        complete_name.create_diamond("NP", "nachname", lastname_str,
                                     [given_names_diamond])
    else: #if name string does not contain ' ', i.e. only last name is given
        complete_name.create_diamond("NP", "nachname", lastname_str, [])

    return complete_name




def lexicalize_keywords(keywords, realize="abstract"):
    """
    @type keywords: C{frozenset} of C{str}

    @type realize: C{str}
    @param realize: "abstract", "complete". 
    "abstract" realizes 'das Thema' / 'die Themen'. 
    "complete" realizes an enumeration of those keywords.
    """
    assert realize in ("abstract", "complete"), \
        "choose 1 of these keyword realizations: abstract, complete"
    num_of_keywords = len(keywords)
    abstract_keywords = __gen_abstract_keywords(num_of_keywords)
    
    if realize == "abstract":
        return abstract_keywords
    
    elif realize == "complete":
        keyword_description = deepcopy(abstract_keywords)        
        keywords = __gen_keywords(keywords, mode="N")
        keyword_description.append_subdiamond(keywords, mode="NOMERG")
        
        add_nom_prefixes(keyword_description)
        add_mode_suffix(keyword_description, mode="N")
        return keyword_description




    
    

def __gen_abstract_keywords(num_of_keywords):
    """generates a Diamond for 'das Thema' vs. 'die Themen' """
    abstract_keywords = Diamond()

    if num_of_keywords == 1:
        num_prop = "sing"
    if num_of_keywords > 1:
        num_prop = "plur"

    num = Diamond()
    num.create_diamond("NUM", "", num_prop, [])
    art = Diamond()
    art.create_diamond("ART", "sem-obj", "def", [])

    abstract_keywords.create_diamond("", "art", "Thema", [num, art])
    return abstract_keywords


def __gen_keywords(keywords, mode="N"):
    """
    takes a list of keyword (strings) and converts them into a nested
    C{Diamond} structure

    @type keywords: C{list} of C{str}
    @rtype: C{Diamond}
    """
    assert isinstance(keywords, list), "input needs to be a list"
    
    def gen_keyword(keyword, mode="N"):
        """takes a keyword (string) and converts it into a C{Diamond}"""
        fixed_keyword = keyword.replace(" ", "_")
        num = Diamond()
        num.create_diamond("NUM", "", "sing", [])
        keyword_diamond = Diamond()
        keyword_diamond.create_diamond(mode, "sorte", fixed_keyword, [num])
        return keyword_diamond

    if isinstance(keywords, list) and len(keywords) == 1:
        return gen_keyword(keywords[0], mode="N")

    elif isinstance(keywords, list) and len(keywords) > 1:
        keyword_diamonds = [gen_keyword(kw, mode="N") for kw in keywords]
        return __gen_enumeration(keyword_diamonds, mode="N") # TODO: dbg,rm


def lexicalize_year(year, title, realize="complete"): #TODO: authors should be args*
    """___ ist 1986 erschienen.
    
    TODO: change nom prefix rules: 1986 -> n1:modus
    """
    tempus = Diamond()
    tempus.create_diamond("TEMP:tempus", "", "imperf", [])

    adv = Diamond()
    adv.create_diamond("ADV", "modus", year, [])

    agens = lexicalize_titles(title, realize)
    agens[Feature("mode")] = "AGENS"
    
    aux = Diamond()
    aux.create_diamond("AUX", "sein", "sein", [tempus, adv, agens])

    
    erschienen = Diamond()
    erschienen.create_diamond("", "inchoativ", "erscheinen", [aux])

    remove_nom_prefixes(erschienen) #lexicalize_titles() already has prefixes
    add_nom_prefixes(erschienen)
    return erschienen


def __gen_enumeration(diamonds_list, mode=""):
    """
    Takes a list of Diamond instances and combines them into a nested Diamond.
    This nested Diamond can be used to generate an enumeration, such as::

        A
        A und B
        A, B und C
        A, B, C und D
        ...

    @type diamonds_list: C{list} of C{Diamond}s

    @rtype: C{Diamond}
    @return: a Diamond instance (containing zero or more nested Diamond
    instances)
    """
    if len(diamonds_list) is 0:
        return []
    if len(diamonds_list) is 1:
        return diamonds_list[0]
    if len(diamonds_list) is 2:
        enumeration = Diamond()
        enumeration.create_diamond(mode, "konjunktion", "und", diamonds_list)
    if len(diamonds_list) > 2:
        enumeration = Diamond()
        nested_komma_enum = __gen_komma_enumeration(diamonds_list[:-1], mode)
        enumeration.create_diamond(mode, "konjunktion", "und",
                                   [nested_komma_enum, diamonds_list[-1]])
    return enumeration


def __gen_komma_enumeration(diamonds_list, mode=""):
    """
    This function will be called by __gen_enumeration() and takes a list of
    Diamond instances and combines them into a nested Diamond, expressing comma
    separated items, e.g.:

        Manning, Chomsky
        Manning, Chomsky, Allen
        ...

    @type diamonds_list: C{list} of C{Diamond}s

    @rtype: C{Diamond}
    @return: a Diamond instance (containing zero or more nested Diamond
    instances)
    """
    if len(diamonds_list) == 0:
        return []
    if len(diamonds_list) == 1:
        return diamonds_list[0]
    if len(diamonds_list) == 2:
        komma_enum = Diamond()
        komma_enum.create_diamond(mode, "konjunktion", "komma", diamonds_list)
    if len(diamonds_list) > 2:
        komma_enum = Diamond()
        nested_komma_enum = __gen_komma_enumeration(diamonds_list[:-1], mode)
        komma_enum.create_diamond(mode, "konjunktion", "komma",
                                  [nested_komma_enum, diamonds_list[-1]])
    return komma_enum


def __split_name(name):
    """
    naively splits a name string into a last name and a given name
    (or given names).

    @type name: C{Str}
    @param name: a name, e.g. "George W. Bush"

    @rtype: C{tuple} of (C{list}, C{str}), where C{list} consists of C{str}s
    @return: a list of given names and a string containing the last name
    """
    name_components = name.split()
    given_names, last_name = name_components[:-1], name_components[-1]
    return given_names, last_name


def __create_nested_given_names(given_names):
    """
    given names are represented as nested (diamond) structures in HLDS
    (instead of using indices to specify the first given name, second given
    name etc.), where the last given name is the outermost structural
    element and the first given name is the innermost one.

    @type given_names: C{list} of C{str}
    @rtype: empty C{list} or C{Diamond}
    @return: returns an empty list if given_names is empty. otherwise returns a
    C{Diamond} (which might contain other diamonds)
    """
    if given_names:
        preceding_names, last_given_name = given_names[:-1], given_names[-1]
        diamond = Diamond()
        nested_diamond = __create_nested_given_names(preceding_names)

        if type(nested_diamond) is list:
            diamond.create_diamond("N1", "vorname", last_given_name,
                                   nested_diamond)
        elif type(nested_diamond) is Diamond:
            diamond.create_diamond("N1", "vorname", last_given_name,
                                   [nested_diamond])
        return diamond

    else: # given_names list is empty
        return []


def gen_personal_pronoun(count, gender, person):
    """
    @type count: C{int}
    @param count: 1 for 'singular'; > 1 for 'plural'
    
    @type gender: C{str}
    @param gender: 'masc', 'fem' or 'neut'
    
    @type person: C{int}
    @param person: 1 for 1st person, 2 for 2nd person ...
    """
    if count == 1:
        numerus = "sing"
    else:
        numerus = "plur"

    if numerus == "plur" or gender == "":
        gender = "fem" # there should be no gender marker in plural, 
                       # but that doesn't always work with ccg-realize
        
    person_prop_str = "{0}te".format(str(person)) # 3 -> 3te
    
    pers = Diamond()
    pers.create_diamond("PERS", "", person_prop_str, [])
    pro = Diamond()
    pro.create_diamond("PRO", "", "perspro", [])
    gen = Diamond()
    gen.create_diamond("GEN", "", gender, [])
    num = Diamond()
    num.create_diamond("NUM", "", numerus, [])
            
    pronoun = Diamond()
    pronoun.create_diamond("", "sem-obj", "", [pers, pro, gen, num])
    return pronoun
