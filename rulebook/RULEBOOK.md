# CiteSure rulebook v1 — for review

Generated from `rulebook/*.yaml` by `tools/rulebook_report.py`. Do not edit by hand.

- **44 source types** (templates), 3 cited in the text only, 6 deferred
- **78 rules**: 74 errors, 4 needs review
- Rules by source: Guide text 45, Project ruling 11, Guide template 9, Derived — please confirm 8, Guide examples 5
- **32 guide examples** excluded or corrected because they contain mistakes

## 1. What to check first

### 1.1 Rules that come from project rulings

The rulings as reports quote them (`rulings` in `rules.yaml`; full text: spec §6):

| Ruling | Text |
|---|---|
| 6.1 Dashes in page ranges | Page ranges use an en dash (21–27) or a hyphen (21-27); the guide accepts both. Any other dash, such as an em dash, and spaces around the dash are errors. |
| 6.2 DOI and URL | A DOI is written once, as https://doi.org/10.xxxx (not doi:, dx.doi.org or a library proxy address such as doi-org.ezproxy.aut.ac.nz), with no full stop after it, and never together with "Retrieved from". An online article without a DOI gives "Retrieved from" and the journal's homepage URL, not the article, database or PMC address. An article with neither a DOI nor a URL matches the guide's print template and is accepted. |
| 6.3 Article numbers | An article number in place of page numbers (Insects, 13(9), 836.) is accepted as written. |
| 6.4 Publisher location | The place of publication is required for every publisher: City, Country/State: Publisher. |
| 6.5 Reference list heading | The reference list needs a heading. "References" and "Literature Cited", in capitals or not, are accepted. |
| 6.6 Layout of the reference list | A hanging indent of about 0.5 inch (0.4–0.6 inch accepted); the guide's "5–7 spaces" is old typing advice. Line spacing is not checked: it belongs to the university's thesis format. |
| 6.7 Italics | Journals: the journal name and the volume are italic; the issue, pages and article title are not. Books, reports, webpages and videos: the title is italic. Chapters: the book title is italic, the chapter title is not. |
| 6.8 Merged references | Two references run together in one entry are an error; each part is checked on its own. A continuation line that only looks like a new reference is not an error. |
| 6.9 Guide mistakes and matching | Mistakes in the guide's own examples are never accepted, and an in-text citation must always match its reference: the same spelling of the authors' names and the same year. |

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| LST-HEADING-01 | The reference list has a heading | Error | list | Project ruling, spec §6.5 |
| LST-HEADING-02 | Heading is "References" or "Literature Cited" | Needs review | list | Project ruling, spec §6.5, `referencelist` › Reference formatting guide<br>“Include the title 'References' (one word, beginning with a capital letter, centred, and not in italics” |
| LST-MERGED-01 | Two references are merged into one entry | Error | list | Project ruling, spec §6.8 |
| LAY-INDENT-01 | Hanging indent of about 0.5 inch (0.4–0.6 accepted) | Error | list | Project ruling, spec §6.6, `referencelist` › Reference formatting guide<br>“Hanging indent your references (space bar in 5 - 7 spaces for the second and subsequent lines of each reference)” |
| REF-JRNL-04 | Page range or article number after the volume/issue (article number accepted as written, ruling 6.3); journals and magazines without 'p.', newspapers with 'p.'/'pp.' | Error | group:journal | Guide text, spec §6.3, `articles` › Magazines & newspapers<br>“Page numbers (if shown online): Magazines - include the numbers only, no p.; Newspapers - use p. or pp.” |
| REF-PUB-01 | Publisher location is given whenever a publisher is given | Error | all | Project ruling, spec §6.4 |
| REF-DOI-01 | DOI written as https://doi.org/10.xxxx (not doi:, dx.doi.org or a library proxy link) | Error | all | Project ruling, spec §6.2, `articles` › DOI and URL<br>“A new citing format for DOI was introduced by APA in March 2017. The new format includes https and the prefix doi.org”<br>The same guide section also says: 'Articles retrieved from library databases may include ezproxy.aut.ac.nz in the DOIs. This ezproxy information should be removed.' |
| REF-DOI-03 | The DOI appears once, with a single prefix | Error | all | Project ruling, spec §6.2 |
| REF-DOI-05 | A DOI is not combined with "Retrieved from" | Error | all | Project ruling, spec §6.2 |
| REF-URL-01 | Journal article without a DOI uses the journal's homepage URL, not the article URL or a database/PMC link | Error | journal_article_no_doi_online, magazine_article, newspaper_article, newspaper_article_no_author | Project ruling, spec §6.2, `articles` › DOI and URL<br>“Use the URL of the journal homepage, NOT the full URL of the article, in your reference.” |
| FMT-DASH-01 | Page ranges use an en dash (21–27) or a hyphen (21-27); any other dash, such as an em dash, is wrong | Error | all | Guide text, spec §6.1, `referencelist` › Reference formatting guide<br>“Use an en dash, NOT a hyphen, for page ranges: e.g. 21–27. … NB: If your keyboard will not produce an en dash, it is acceptable to use a hyphen instead.” |
| FMT-ITAL-01 | Journal, magazine and newspaper names and the volume number are italic; issue, pages and article title are not | Error | group:journal | Guide examples, spec §6.7<br>Shown in every journal template and example in the guide. |
| FMT-ITAL-03 | Chapter or entry title not italic; the book or work title italic | Error | book_chapter, ebook_chapter, dictionary_entry_online, symposium_contribution, tv_episode | Guide examples, spec §6.7<br>Shown in the guide's examples Easton (2008), Root (2007) and Helmig & Thaler (2010). |
| MAT-03 | Year differs between the citation and the reference | Error | in_text | Project ruling, spec §6.9<br>An in-text citation must always match its reference |
| MAT-04 | Author name spelt differently in the citation and the reference | Error | in_text | Project ruling, spec §6.9 |

### 1.2 Rules not stated in the guide (derived) — please confirm

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| LST-DUP-01 | The same reference appears more than once | Error | list | Derived — please confirm<br>A reference list lists each source once |
| LST-STYLE-01 | The reference is written in a different citation style (e.g. Vancouver) | Error | list | Derived — please confirm<br>The whole reference list must follow APA 6th. A reference in another style, such as Vancouver or a numbered style, does not. |
| LST-TYPE-01 | Source type could not be determined, or is not covered by rulebook v1 | Needs review | list | Derived — please confirm<br>CiteSure could not tell which kind of source this is, or the guide has no template for it, so the format could not be checked. |
| REF-TITLE-03 | Titles must not be written in capital letters throughout | Error | all | Derived — please confirm<br>Follows from the guide's capitalisation rules for titles (REF-TITLE-01 sentence style, REF-TITLE-02 headline style): neither writes a title in capital letters throughout. |
| REF-JRNL-01 | Journal name written in full, not abbreviated | Error | group:journal | Derived — please confirm<br>The guide's journal templates give the full 'Title of the Journal' in headline style, and none of its examples abbreviates a journal name. |
| FMT-SPACE-01 | Missing space between elements (e.g. '640.Dee') | Error | all | Derived — please confirm<br>Every template and example in the guide puts a space after the punctuation that separates two elements. |
| MAT-05 | The citation could refer to more than one reference — add authors or initials to tell them apart | Error | in_text | Derived — please confirm<br>Follows from the guide's et al. and same-surname rules: a citation must point to exactly one reference. |
| REC-01 | Share of references from the last 5 years meets the required share | Error | list | Derived — please confirm<br>University synopsis rule, not APA. Off by default. |

### 1.3 Guide pages not covered by rulebook v1

References of these types are reported as *Needs review: source type not covered*.

- `legislation`: New Zealand legislation and case law
- `health`: Specific health examples (data sheets, clinical resources)
- `tables`: Tables, figures and images
- `page-4586645`: Exhibition catalogue
- `software` › Computer games: Game Studies format, not APA
- `blogs` › Facebook or Twitter message: Guide links to the APA blog only; no format given

## 2. All rules

### Whole reference list

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| LST-HEADING-01 | The reference list has a heading | Error | list | Project ruling, spec §6.5 |
| LST-HEADING-02 | Heading is "References" or "Literature Cited" | Needs review | list | Project ruling, spec §6.5, `referencelist` › Reference formatting guide<br>“Include the title 'References' (one word, beginning with a capital letter, centred, and not in italics” |
| LST-ORDER-01 | References are in alphabetical order of the first author's surname (or title when there is no author) | Error | list | Guide text, `books` › Newspaper article online, no author (PDF)<br>“No author: alphabetise by first significant title word.” |
| LST-ORDER-02 | Same first author — order by year, earlier first; same first author with different co-authors — order by the next author | Error | list | Guide text, `referencelist` › Reference formatting guide<br>“Order by year of publication, the earlier one first. … Same first author, different second author: Order alphabetically by second or subsequent authors” |
| LST-ORDER-03 | Same author(s) and same year — add a, b … after the year | Error | list | Guide text, `referencelist` › Reference formatting guide<br>“Same year of publication for both - add 'a' and 'b' after the year, inside the brackets. Include this in the in text citation.” |
| LST-DUP-01 | The same reference appears more than once | Error | list | Derived — please confirm<br>A reference list lists each source once |
| LST-INTEXTONLY-01 | Personal communications, whole websites and social-media feeds are cited in the text only, not in the reference list | Error | list | Guide text, `personalcommunications` › Personal communications<br>“No entry in the reference list is needed as personal communications are unable to be retrieved.” |
| LST-MERGED-01 | Two references are merged into one entry | Error | list | Project ruling, spec §6.8 |
| LST-STYLE-01 | The reference is written in a different citation style (e.g. Vancouver) | Error | list | Derived — please confirm<br>The whole reference list must follow APA 6th. A reference in another style, such as Vancouver or a numbered style, does not. |
| LST-TYPE-01 | Source type could not be determined, or is not covered by rulebook v1 | Needs review | list | Derived — please confirm<br>CiteSure could not tell which kind of source this is, or the guide has no template for it, so the format could not be checked. |

### Layout

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| LAY-INDENT-01 | Hanging indent of about 0.5 inch (0.4–0.6 accepted) | Error | list | Project ruling, spec §6.6, `referencelist` › Reference formatting guide<br>“Hanging indent your references (space bar in 5 - 7 spaces for the second and subsequent lines of each reference)” |

### Authors and editors

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-AUTH-01 | Personal authors are written Surname, Initials — initials with full stops and spaces (Alred, G. J.) | Error | all | Guide template, `books` › Reference format for print books<br>“Author, Initial. (Year). Book title. City of publication, Country/State: Publisher.” |
| REF-AUTH-02 | Use '&' before the final author, preceded by a comma (Li, S., & Seale, C.) | Error | all | Guide text, `referencelist` › Reference formatting guide<br>“Ampersand: Use for 2 - 6 authors, use "&" before the final author” |
| REF-AUTH-03 | One to seven authors — list all of them | Error | all | Guide text, `referencelist` › Four to seven authors<br>“List all authors in the reference entry” |
| REF-AUTH-04 | Eight or more authors — first six, an ellipsis, then the last author | Error | all | Guide text, `referencelist` › More than seven authors<br>“First 6 authors ... last author. and follow by date and other information.” |
| REF-AUTH-05 | Editors of a chapter's book: initials before surname, with (Ed.) for one and (Eds.) for several | Error | book_chapter, ebook_chapter, symposium_contribution, tv_episode | Guide text, `brief-guide-pdf` › Book chapter<br>“Editors: first name initial. surname.” |
| REF-AUTH-06 | Edited book: editors inverted, followed by (Ed.) or (Eds.) matching their number | Error | edited_book, journal_special_issue, book_multivolume | Guide template, `books` › Edited book<br>“Sykes, P., & Potts, A. (Eds.). (2008). …” |

### Dates

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-DATE-01 | Year in brackets after the author, followed by a full stop: (2008). | Error | all | Guide template, `articles` › Journal articles - online<br>“Author, Initial. (Year). Title of the article” |
| REF-DATE-02 | No date: (n.d.); not yet published: (in press) | Error | all | Guide text, `brief-guide-pdf` › Website html - no date<br>“Reference List and In text: (n.d.) for no date.” |
| REF-DATE-03 | Magazines, newspapers, blogs and online videos give the exact date: (2009, April 23) | Error | magazine_article, newspaper_article, newspaper_article_no_author, blog_post, online_video, online_video_series | Guide text, `brief-guide-pdf` › Magazine article online<br>“Reference List: Give the exact date of the article.” |

### Titles and capitalisation

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-TITLE-01 | Titles of articles, chapters, books, reports and web pages in sentence case | Error | all | Guide text, `referencelist` › Reference formatting guide<br>“Book title or article title (in a journal, magazine or newspaper) - use sentence style; i.e. capitalise the first word of the title, and subtitle (after the colon), and any proper names” |
| REF-TITLE-02 | Journal titles in headline style (all words capitalised except articles and prepositions) | Error | group:journal, conference_paper_online | Guide text, `referencelist` › Reference formatting guide<br>“Journal title - use headline style; i.e. capitalise all the words, except articles and prepositions” |
| REF-TITLE-03 | Titles must not be written in capital letters throughout | Error | all | Derived — please confirm<br>Follows from the guide's capitalisation rules for titles (REF-TITLE-01 sentence style, REF-TITLE-02 headline style): neither writes a title in capital letters throughout. |

### Journals

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-JRNL-01 | Journal name written in full, not abbreviated | Error | group:journal | Derived — please confirm<br>The guide's journal templates give the full 'Title of the Journal' in headline style, and none of its examples abbreviates a journal name. |
| REF-JRNL-02 | Journal article has a volume number | Error | journal_article, journal_article_no_doi_online, journal_special_issue | Guide template, `articles` › Journal articles - in print<br>“Title of the Journal, volume(issue if used), pages.” |
| REF-JRNL-03 | Issue in brackets straight after the volume, no space: 17(10) | Error | group:journal | Guide template, `articles` › Journal articles - in print<br>“Title of the Journal, volume(issue if used), pages.” |
| REF-JRNL-04 | Page range or article number after the volume/issue (article number accepted as written, ruling 6.3); journals and magazines without 'p.', newspapers with 'p.'/'pp.' | Error | group:journal | Guide text, spec §6.3, `articles` › Magazines & newspapers<br>“Page numbers (if shown online): Magazines - include the numbers only, no p.; Newspapers - use p. or pp.” |

### Books, reports, theses, conferences, software

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-BOOK-01 | Edition after the title in brackets, not italic: (3rd ed.) | Error | group:book | Guide template, `books` › New edition of a book<br>“Berk, L. E. (2004). Development through the lifespan (3rd ed.). Boston, MA: Allyn and Bacon.” |
| REF-BOOK-02 | Chapter: page range in brackets after the book title (pp. 97–106) | Error | book_chapter, ebook_chapter | Guide text, `brief-guide-pdf` › Book chapter<br>“the main entry in your list is the author of the chapter include the page numbers of the chapter.” |
| REF-BOOK-03 | Reprint or translation: (Original work published year) at the end | Error | book_reprint_translation | Guide text, `books` › Reprints and translations<br>“give the date of the version that you have read after the author; put the date of the original publication at the end” |
| REF-REPORT-01 | Report number in brackets straight after the title: (Report No. 06.3) | Error | report_print, report_online | Guide text, `reports` › Other types of reports<br>“Give the report number in parentheses ( ... ) immediately after the title” |
| REF-THESIS-01 | Thesis: degree type in brackets after the title; full university name; location outside the USA | Error | group:thesis | Guide text, `theses` › Thesis from a NZ institutional repository<br>“Include the full URL for the thesis/dissertation and the full name of the degree-granting institution/university. Also include the location of the university, if outside the United States.” |
| REF-CONF-01 | Unpublished conference paper: year and month of the meeting, 'Paper presented at …', location | Error | conference_paper_online, conference_paper_unpublished, symposium_contribution | Guide text, `conferences` › Conference papers and presentations - not formally published<br>“Include the year and the month of the symposium or meeting” |
| REF-SOFT-01 | Software: title not italic, followed by (Version x) and [type of software] | Error | group:software | Guide template, `software` › Computer software and code<br>“Rightsholder, A. A. (year). Title of Software or Program (Version number) [Type of software]. Retrieved from http://xxxxx” |

### Publisher and location

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-PUB-01 | Publisher location is given whenever a publisher is given | Error | all | Project ruling, spec §6.4 |
| REF-PUB-02 | Location format: USA 'City, ST'; elsewhere 'City, Country' in full | Error | all | Guide text, `referencelist` › Reference formatting guide<br>“USA publishers give the city in full and the abbreviation for the state. … Publishers outside the USA: Give the city in full and the country in full” |
| REF-PUB-03 | When the author is also the publisher, write 'Author' as the publisher | Error | group:book, group:report, manual | Guide text, `books` › Corporate author as publisher<br>“In the reference list, where the author and publisher are the same, use the word Author in the publisher position.” |

### Square-bracket descriptions

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-DESC-01 | Format description in square brackets straight after the title: [Video file], [Blog post], [PowerPoint slides] | Error | group:av, group:social, group:software, web_document, course_material, ebook_url, journal_special_issue | Guide text, `referencelist` › Use of square brackets<br>“If format, medium or description information is important for a resource to be retrieved or identified, use square brackets after the title to include this detail” |

### DOI

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-DOI-01 | DOI written as https://doi.org/10.xxxx (not doi:, dx.doi.org or a library proxy link) | Error | all | Project ruling, spec §6.2, `articles` › DOI and URL<br>“A new citing format for DOI was introduced by APA in March 2017. The new format includes https and the prefix doi.org”<br>The same guide section also says: 'Articles retrieved from library databases may include ezproxy.aut.ac.nz in the DOIs. This ezproxy information should be removed.' |
| REF-DOI-02 | No full stop after a DOI | Error | all | Guide text, `articles` › DOI and URL<br>“No full stop at the end of a DOI.” |
| REF-DOI-03 | The DOI appears once, with a single prefix | Error | all | Project ruling, spec §6.2 |
| REF-DOI-05 | A DOI is not combined with "Retrieved from" | Error | all | Project ruling, spec §6.2 |

### URLs and retrieval statements

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REF-URL-01 | Journal article without a DOI uses the journal's homepage URL, not the article URL or a database/PMC link | Error | journal_article_no_doi_online, magazine_article, newspaper_article, newspaper_article_no_author | Project ruling, spec §6.2, `articles` › DOI and URL<br>“Use the URL of the journal homepage, NOT the full URL of the article, in your reference.” |
| REF-URL-02 | Items from a library database give the database homepage only | Error | ebook_url, report_database, thesis_database, database_article_no_author | Guide text, `referencelist` › DOI and URL<br>“Do not use the full URL of the source that you retrieved from a database.” |
| REF-URL-03 | Retrieval date only for content likely to change (HTML pages, wikis); never for PDFs, journals, magazines, newspapers or videos | Error | all | Guide text, `websites` › Webpages - html<br>“html websites are likely to change or be updated → do usually include a date of retrieval. PDF documents are not likely to change → don't include a date of retrieval.” |
| REF-URL-04 | HTML web page without a retrieval date | Needs review | webpage, webpage_no_author, dictionary_entry_online | Guide text, `websites` › Webpages - html<br>“Generally, if a webpage could change do include the date you retrieved it” |
| REF-URL-05 | 'Retrieved from URL', or 'Retrieved Month day, year, from URL' when a retrieval date is given | Error | all | Guide template, `websites` › Webpages<br>“Author, A. (date). Title of document [Format description]. Retrieved from http://xxx” |
| REF-URL-06 | No full stop after a URL | Error | all | Guide examples<br>No guide example ends a URL with a full stop (the one exception, Austen 1853, is excluded) |

### Typography: dashes, italics, order, spacing

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| FMT-DASH-01 | Page ranges use an en dash (21–27) or a hyphen (21-27); any other dash, such as an em dash, is wrong | Error | all | Guide text, spec §6.1, `referencelist` › Reference formatting guide<br>“Use an en dash, NOT a hyphen, for page ranges: e.g. 21–27. … NB: If your keyboard will not produce an en dash, it is acceptable to use a hyphen instead.” |
| FMT-DASH-02 | No spaces around the en dash in a page range | Error | all | Guide text, `referencelist` › Reference formatting guide<br>“No gaps between the page numbers and the en dash.” |
| FMT-ITAL-01 | Journal, magazine and newspaper names and the volume number are italic; issue, pages and article title are not | Error | group:journal | Guide examples, spec §6.7<br>Shown in every journal template and example in the guide. |
| FMT-ITAL-02 | Titles of books, reports, web pages, web documents, theses, videos and standards are italic | Error | group:book, group:report, group:web, group:thesis, group:av, group:standard, conference_paper_online, conference_paper_unpublished | Guide text, `books` › No author<br>“italics for the title of a journal or book or brochure or report” |
| FMT-ITAL-03 | Chapter or entry title not italic; the book or work title italic | Error | book_chapter, ebook_chapter, dictionary_entry_online, symposium_contribution, tv_episode | Guide examples, spec §6.7<br>Shown in the guide's examples Easton (2008), Root (2007) and Helmig & Thaler (2010). |
| FMT-ITAL-04 | Not italic: blog post titles, series videos, software titles | Error | blog_post, online_video_series, software, software_no_author | Guide text, `blogs` › Blogs<br>“Blog posts are part of a series and so the title of the post is not in italics” |
| FMT-ORDER-01 | Elements in the order and with the punctuation of the source type's template | Error | all | Guide template<br>The guide's template for this kind of source. |
| FMT-SPACE-01 | Missing space between elements (e.g. '640.Dee') | Error | all | Derived — please confirm<br>Every template and example in the guide puts a space after the punctuation that separates two elements. |

### In-text citations

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| CIT-AMP-01 | '&' between authors inside brackets; 'and' in running text | Error | in_text | Guide text, `intextcitation` › Authors - summary<br>“in brackets use & between authors … in a sentence use and between authors” |
| CIT-PUNCT-01 | Comma before the year and before '&' with three or more authors: (Alred, Brusaw, & Oliu, 2009) | Error | in_text | Guide examples, `intextcitation` › Three, four or five authors<br>“(Alred, Brusaw, & Oliu, 2009)” |
| CIT-ETAL-01 | One or two authors — name both in every citation | Error | in_text | Guide text, `intextcitation` › Authors - summary<br>“1-2: Both authors \| Both authors” |
| CIT-ETAL-02 | Three to five authors — all names in the first citation, then first author et al. | Error | in_text | Guide text, `intextcitation` › Authors - summary<br>“3-5: All authors \| First author et al.” |
| CIT-ETAL-03 | Six or more authors — first author et al. from the first citation | Error | in_text | Guide text, `intextcitation` › Authors - summary<br>“6-7: First author et al. \| First author et al. … 8+: First author et al.” |
| CIT-ETAL-04 | 'et al.' written with a full stop after 'al' | Error | in_text | Guide examples, `intextcitation` › Three, four or five authors<br>“(Alred et al., 2009)” |
| CIT-CORP-01 | Corporate author abbreviation introduced in the first citation [IRD], then used | Error | in_text | Guide text, `books` › Corporate author (organization)<br>“The first time you cite it in-text, write the corporate author in full with its abbreviation in square brackets "[...]" plus date. In subsequent citations use the abbreviation plus date.” |
| CIT-MULTI-01 | Several works in one bracket — alphabetical order, separated by semicolons | Error | in_text | Guide text, `intextcitation` › Two or more citations<br>“Same alphabetical order as in your reference list. Separated by a semi colon ;” |
| CIT-MULTI-02 | Several works by the same author — name once, years in order: (Gogel, 1990, 2006) | Error | in_text | Guide text, `intextcitation` › Two or more citations<br>“Give the authors' surnames once only” |
| CIT-SAME-01 | First authors who share a surname — add initials in every citation | Needs review | in_text | Guide text, `intextcitation` › Authors with the same surname<br>“If lead authors share the same surname, include author's initials in all in-text citations even if the year of publication differs.” |
| CIT-QUOTE-01 | Direct quotes give a page number: p. 378 / pp. 111–112 | Error | in_text | Guide text, `intextcitation` › Direct quotes<br>“Your in-text citation for direct quotations should include author, date, and page numbers.” |
| CIT-NOAUTH-01 | No author — first words of the title in quotation marks (article, web page) or italics (book, report), with capitals | Error | in_text | Guide text, `intextcitation` › No author<br>“Put double quotation marks around the title of an article or a website; use capitals … Periodical, book, brochure or report: Use italics and capitals” |
| CIT-SECOND-01 | Secondary source: '(as cited in Author, year)', and only the secondary source in the reference list | Error | in_text | Guide text, `intextcitation` › Secondary citations<br>“Name the author of the original work in your text, cite the secondary source in in-text citation: (as cited in ..., 1993)” |
| CIT-PERS-01 | Personal communication — initials and an exact date: (I. Tokugawa, personal communication, January 25, 2019) | Error | in_text | Guide text, `personalcommunications` › Personal communications<br>“Include initials and an exact date.” |
| CIT-REPRINT-01 | Reprints and translations give both years: (Freud, 1900/1953) | Error | in_text | Guide text, `books` › Reprints and translations<br>“in text give both dates: (Freud, 1900/1953).” |

### Matching citations and references

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| MAT-01 | Cited in the text but not in the reference list | Error | in_text | Guide text, `referencelist` › Reference List<br>“All references cited in the text must appear in the reference list, except for personal communications” |
| MAT-02 | In the reference list but never cited in the text | Error | list | Guide text, `referencelist` › Reference List<br>“A reference list lists only the sources you refer to in your writing.” |
| MAT-03 | Year differs between the citation and the reference | Error | in_text | Project ruling, spec §6.9<br>An in-text citation must always match its reference |
| MAT-04 | Author name spelt differently in the citation and the reference | Error | in_text | Project ruling, spec §6.9 |
| MAT-05 | The citation could refer to more than one reference — add authors or initials to tell them apart | Error | in_text | Derived — please confirm<br>Follows from the guide's et al. and same-surname rules: a citation must point to exactly one reference. |
| MAT-06 | Year suffix (a, b) used in one place but not the other | Error | in_text | Guide text, `referencelist` › Reference formatting guide<br>“add 'a' and 'b' after the year, inside the brackets. Include this in the in text citation.” |

### Recency (optional, off by default)

| ID | Rule | Level | Applies to | Source |
|---|---|---|---|---|
| REC-01 | Share of references from the last 5 years meets the required share | Error | list | Derived — please confirm<br>University synopsis rule, not APA. Off by default. |

## 3. Source types (templates)

Pattern syntax: `{field}` required · `[ … ]` optional · `{a|b}` one of · `*…*` italic.

### Journal article (print or online) — `journal_article`

Pattern: `{author} ({year}). {title}. *{journal}, {volume}*[({issue})], {pages|article_number}.[ {doi}]`

Source: `articles` › Journal articles - online / Journal articles - in print

- Note: Issue only if used. Article number in place of pages accepted (ruling 6.3).
- Note: DOI when available; no full stop after it (ruling 6.2).
- Note: No DOI and no URL matches the print template and is accepted (ruling 6.2).
- Note: Page range with an en dash or a hyphen (ruling 6.1).
- Example: Li, S., & Seale, C. (2007). Learning to do qualitative data analysis: An observational study of doctoral work. *Qualitative Health Research*, *17*, 1442–1452. https://doi.org/10.1177/1049732307306924
- Example: McFeely, S. (2001). Young people’s pathway to smoking cessation. *Nursing Standard*, *16*(2), 39–42.
- Example: Washington, E. T. (2014). An overview of cyberbully in higher education. *Adult Learning*, *26*(1), 21–27. https://doi.org/10.1177/1045159514558412
- Example: Orazi, D. C., Lei, J., & Bove, L. L. (2015). The nature and framing of gambling consequences in advertising. *Journal of Business Research, 68*(10), 2049-2056. https://doi.org/10.1016/j.jbusres.2015.03.002

### Journal article online, no DOI — `journal_article_no_doi_online`

Pattern: `{author} ({year}). {title}. *{journal}, {volume}*[({issue})], {pages|article_number}. Retrieved from {homepage_url}`

Source: `articles` › Journal articles - online (Article without doi)

- Note: Journal HOMEPAGE URL, not the article URL; no retrieval date.
- Note: A database homepage (e.g. JSTOR) only if the journal has no homepage, is discontinued, or is archive-only.
- Example: Bartlett, R. P. (2009). Going private but staying public: Re-examining the effect of Sarbanes-Oxley on firms going-private decisions. *The University of Chicago Law Review, 76,* 7–39. Retrieved from http://lawreview.uchicago.edu/

### Journal article in press — `journal_article_in_press`

Pattern: `{author} (in press). {title}. *{journal}*. {doi|retrieved_from}`

Source: `articles` › Journal articles - in press

- Example: Brey, P. (in press). The strategic role of technology in a good society. *Technology in Society*. https://doi.org/10.1016/j.techsoc.2017.02.002

### Journal article, advance online publication — `journal_article_advance_online`

Pattern: `{author} ({year}). {title}. *{journal}*. Advance online publication. {doi}`

Source: `articles` › With doi, advance online publication

- Example: Von Ledebur, S. C. (2007). Optimizing knowledge transfer by new employees in companies. *Knowledge Management Research & Practice*. Advance online publication. https://doi.org/10.1057/palgrave.kmrp.8500141

### Entire special issue of a journal — `journal_special_issue`

Pattern: `{editors_inverted} ({ed}). ({year}). {title} [Special issue]. *{journal}, {volume}*({issue}).`

Source: `articles` › Special issues

- Example: Haney, C., & Wiener, R. L. (Eds.). (2004). Capital punishment in the United States [Special issue]. *Psychology, Public Policy, and Law, 10*(4).

### Magazine article (print or online) — `magazine_article`

Pattern: `{author} ({year}, {month}[ {day}]). {title}. *{magazine}*[, *{volume}*][({issue})][, {pages}].[ Retrieved from {homepage_url}]`

Source: `articles` › Magazines & newspapers

- Note: Month for monthlies, month and day for weeklies, season if given.
- Note: Page numbers without p.; no retrieval date; homepage URL of the publication.
- Example: Read, E. (2007, November 1). Myth-busting gen Y. *New Zealand Management*, *54*(10), 63–64. Retrieved from http://www.management.co.nz

### Newspaper article (print or online) — `newspaper_article`

Pattern: `{author} ({year}, {month} {day}). {title}. *{newspaper}*[, {page_prefix} {pages}].[ Retrieved from {homepage_url}]`

Source: `articles` › Magazines & newspapers

- Note: Newspapers use p. or pp. before page numbers.
- Note: No author: the title moves to the author position (see newspaper_article_no_author).
- Example: Zendrian, A. (2008, April 15). CEO pay too high? *The New York Times*. Retrieved from http://www.nytimes.com
- Example: Fleming, G. (2008, November 4). Shaking up the working world. *The New Zealand Herald*, p. D1.

### Newspaper article, no author — `newspaper_article_no_author`

Pattern: `{title}. ({year}, {month} {day}). *{newspaper}*[, {page_prefix} {pages}].[ Retrieved from {homepage_url}]`

Source: `articles` › Magazines & newspapers (No author)

- Example: Nuke test inquiry doubted. (2009, April 23). *The Dominion Post*, p. 5. Retrieved from http://www.stuff.co.nz/dominion-post

### Industry/product article from a library database — `database_article_no_author`

Pattern: `{corporate_author}. ({year}, {month} {day}). *{title}*. Retrieved from {database} database.`

Source: `articles` › Articles from library databases

- Example: Euromonitor International. (2017, January 27). *Coffee in New Zealand*. Retrieved from Passport database.

### Book (print) — `book`

Pattern: `{author} ({year}). *{title}*[ ({edition} ed.)]. {location}: {publisher}.`

Source: `books` › Books (Reference format for print books)

- Note: Publisher location mandatory (ruling 6.4): US City, ST; elsewhere City, Country.
- Note: Edition in brackets after the title, not italic.
- Example: Gambles, I. (2009). *Making the business case: Proposals that succeed for projects that work*. Farnham, England: Ashgate.
- Example: Gazda, G. M., Balzer, F. J., Childers, W. C., Nealy, A. U., Phelps, R. E., & Walters, R. P. (2005). *Human relations development: A manual for educators* (7th ed.). Boston, MA: Pearson Educational.
- Example: Berk, L. E. (2004). *Development through the lifespan* (3rd ed.). Boston, MA: Allyn and Bacon.
- Example: Watson, S., Gunasekara, G., Gedye, M., van Roy, Y., Ross, M., Longdin, L., … Brown, L. (2003). *Law of business organisations* (4th ed.). Auckland, New Zealand: Palatine Press.

### Book, no author — `book_no_author`

Pattern: `*{title}*[ ({edition} ed.)]. ({year}). {location}: {publisher}.`

Source: `books` › No author

- Example: *Collins concise New Zealand dictionary* (7th ed.). (2008). London, England: Collins.

### Book, corporate author is also the publisher — `book_author_as_publisher`

Pattern: `{corporate_author}. ({year}). *{title}*. {location}: Author.`

Source: `books` › Corporate author as publisher

- Example: New Zealand Universities Academic Audit Unit. (1988). *Academic audit reports: Reports of the general academic audits of New Zealand universities*. Wellington, New Zealand: Author.

### Edited book (incl. custom textbooks, proceedings published as a book) — `edited_book`

Pattern: `{editors_inverted} ({ed}). ({year}). *{title}*[ [{description}]]. {location}: {publisher}.`

Source: `books` › Edited book; Book compilations / custom publications

- Example: Sykes, P., & Potts, A. (Eds.). (2008). *Researching education from the inside: Investigations from within*. London, England: Routledge.
- Example: Mpofu, C. (Ed.). (2010). *Psychology and lifespan development: An introductory text for health professionals* [Custom textbook]. North Shore, New Zealand: Pearson Custom Publication.
- Example: Olsson, S., & Stirton, N. (Eds.). (1996). *Women and leadership: Power and practice: International conference, 1996*. Palmerston North, New Zealand: Massey University.

### Chapter in an edited book (print) — `book_chapter`

Pattern: `{author} ({year}). {chapter_title}. In {editors} ({ed}), *{book_title}* ([{edition} ed., ]pp. {pages}). {location}: {publisher}.`

Source: `books` › Chapter from an edited book

- Note: Chapter title not italic; book title italic; editors with initials first.
- Example: Easton, B. (2008). Does poverty affect health? In K. Dew & A. Matheson (Eds.), *Understanding health inequalities in Aotearoa New Zealand* (pp. 97–106). Dunedin, New Zealand: Otago University Press.
- Example: Root, J. (2007). Film noir. In P. Cook (Ed.), *The cinema book* (3rd ed., pp. 305–315). London, England: British Film Institute.

### Several volumes in a multivolume work — `book_multivolume`

Pattern: `{editors_inverted} ({ed}). ({year_range}). *{title}* (Vols. {volumes}). {location}: {publisher}.`

Source: `books` › Several volumes in a multivolume work

- Example: Koch, S. (Ed.). (1959-1963). *Psychology: A study of science* (Vols. 1-6). New York, NY: McGraw-Hill.

### Reprint, translation or classical work — `book_reprint_translation`

Pattern: `{author} ({year}). *{title}*[ ({translator}, Trans.)]. {location}: {publisher}. (Original work published {original_year})`

Source: `books` › Reprints and translations; Classical works

- Note: In text give both dates: (Freud, 1900/1953).
- Example: Plato. (1961). *Meno* (R. S. Bluck, Trans.). Cambridge, England: Cambridge University Press. (Original work published ca. 380 B.C.)

### E-book with DOI — `ebook_doi`

Pattern: `{author} ({year}). *{title}*. {doi}`

Source: `books` › ebook - with DOI

- Example: Schiraldi, G. R. (2001). *The post-traumatic stress disorder sourcebook: A guide to healing, recovery, and growth*. https://doi.org/10.1036/0071393722

### E-book without DOI (Kindle, free online, library database) — `ebook_url`

Pattern: `{author} ({year}). *{title}*[ [{description}]]. Retrieved from {url}`

Source: `books` › ebook - Kindle / free online / via the AUT Library

- Note: Library database: homepage URL only, ezproxy removed.
- Example: Gladwell, M. (2008). *Outliers: The story of success* [Kindle DX version]. Retrieved from http://www.amazon.com
- Example: Mollison, M. (2010). *Producing videos: A complete guide*. Retrieved from http://www.proquest.com

### Chapter in an edited e-book — `ebook_chapter`

Pattern: `{author} ({year}). {chapter_title}. In {editors} ({ed}), *{book_title}*[ ({edition} ed.)][ (pp. {pages})]. {doi|retrieved_from}`

Source: `books` › Chapter in an edited ebook - with DOI / not from AUT Library

- Example: Helmig, B., & Thaler, J. (2010). Nonprofit marketing. In R. Taylor (Ed.), *Third sector research* (pp. 151–169). https://doi.org/10.1007/978-1-4419-5707-8_12

### Online dictionary or encyclopedia entry (incl. wikis) — `dictionary_entry_online`

Pattern: `{term}. ({year|nd}). In *{work}*[ ({edition} ed.)]. Retrieved [{retrieval_date}, from|from] {url}`

Source: `books` › Online dictionary definition; websites: Wikis

- Example: Light. (n.d.). In *Merriam-Webster’s online dictionary* (11th ed.). Retrieved from http://www.merriam-webster.com/dictionary/light
- Example: Global warming. (n.d.). In *Wikipedia*. Retrieved December 6, 2009, from http://en.wikipedia.org/wiki/Global_warming

### Web page (HTML) — `webpage`

Pattern: `{author} ({year|nd}). *{title}*[ [{description}]]. Retrieved [{retrieval_date}, from|from] {url}`

Source: `websites` › Webpages - html

- Note: HTML pages are likely to change: usually include the retrieval date.
- Note: Format description in brackets only when out of the ordinary.
- Example: Flesch, R. (n.d.). *How to write plain English*. Retrieved April 12, 2009, from http://www.mang.canterbury.ac.nz/writing_guide/writing/flesch.shtml
- Example: Department of Internal Affairs. (n.d.). *History of daylight saving*. Retrieved October 29, 2012, from http://www.dia.govt.nz/Daylight-Saving-History

### Web page, no author — `webpage_no_author`

Pattern: `*{title}*. ({year|nd}). Retrieved [{retrieval_date}, from|from] {url}`

Source: `websites` › Webpage – no author

- Example: *Rugby World Cup 2011 pools announced*. (2008). Retrieved May 1, 2009, from http://www.rugbyworldcup.com/mediazone/news/newsid=2027914.html

### Document on a website (PDF, PowerPoint, press release, annual report) — `web_document`

Pattern: `{author} ({year}). *{title}*[ [{description}]]. Retrieved from {url}`

Source: `websites` › PDFs and PowerPoints - documents from websites; Press release

- Note: PDFs are not likely to change: no retrieval date.
- Example: Ministry of Health. (2010). *Customary tattooing guidelines for operators*. Retrieved from http://www.moh.govt.nz/moh.nsf/pagesmh/10068/$File/customary-tattooing-guidelines-for-operators-apr2010v2.pdf
- Example: Sontheimer, R. (2009). *Changes in APA formatting: APA 6th edition* [PowerPoint slides]. Retrieved from http://www.writing.ku.edu/~writing/guides/documents/NewAPA.ppt
- Example: King Fish Media. (2010). *The perfect marriage of content and technology: Is social media the new CRM?* [Press release]. Retrieved from http://www.prnewswire.com/news-releases/the-perfect-marriage-of-content-and-technology--is-social-media-the-new-crm-100760344.htm

### Lecture or course notes / slides from a learning system — `course_material`

Pattern: `{author} ({year}). *{title}* [{description}]. {paper_name}. Retrieved from {url}`

Source: `lecturenotes` › Lecture notes

- Example: Furbish, D. (2009). *Developmental career theory* [Course notes]. Work in Careers 297300. Retrieved from https://blackboard.aut.ac.nz

### Report (print) — `report_print`

Pattern: `{author} ({year}). *{title}*[ ({report_number})]. {location}: {publisher}.`

Source: `reports` › Other types of reports (Reference format for print report)

- Example: Waitangi Tribunal. (2015). *He Whiritaunoka: The Whanganui land report* (Report no. Wai 903). Lower Hutt, New Zealand: Legislation Direct.

### Report (online) — `report_online`

Pattern: `{author} ({year}). *{title}*[ ({report_number})]. Retrieved from [{publisher} website: ]{url}`

Source: `reports` › Online reports

- Note: Name the publisher in the retrieval statement when it is not the author.
- Example: Kessy, S. S. A., & Urio, F. M. (2006). *The contribution of microfinance institutions to poverty reduction in Tanzania* (Research Report No. 06.3). Retrieved from Research on Poverty Alleviation website: http://www.repoa.or.tz/documents_storage/Publications/Reports/06.3_Kessy_and_Urio.pdf
- Example: Ministry of Health. (2007). *Diabetes surveillance: Population-based estimates and projections for New Zealand, 2001–2011* (Public Health Intelligence Occasional Bulletin No. 46). Retrieved from http://www.moh.govt.nz/moh.nsf/pagesmh/6796/$File/diabetes-suveillance-population-estimates-projections-2001-2011.pdf

### Report from a library database (incl. ERIC) — `report_database`

Pattern: `{author} ({date}). *{title}*. Retrieved from {database} database.[ ({accession_number})]`

Source: `reports` › Reports from Library databases; ERIC document

- Example: Auckland International Airport. (2008). *We're in a great place: Annual report 2008*. Retrieved from NZX Company Research database.
- Example: Brewster, C., & Railsback, J. (2002). *Full-day kindergarten: Exploring an option for extended learning*. Retrieved from ERIC database. (ED472733)

### Thesis from a commercial database — `thesis_database`

Pattern: `{author} ({year}). *{title}* ({degree}). Available from {database}. ({accession_number})`

Source: `theses` › Theses and dissertations from online sources

- Example: Pflieger, J. C. (2009). *Adolescents' parent and peer relations and romantic outcomes in young adulthood* (Doctoral dissertation). Available from ProQuest Dissertations & Theses Global database. (UMI No. 3371229)

### Thesis from an institutional repository — `thesis_repository`

Pattern: `{author} ({year}). *{title}* ({degree}, {institution}, {location}). Retrieved from {url}`

Source: `theses` › Thesis from a NZ institutional repository

- Note: Full name of the university; its location if outside the USA.
- Example: Thomas, R. (2009). *The making of a journalist: The New Zealand way* (Doctoral thesis, Auckland University of Technology, Auckland, New Zealand). Retrieved from http://hdl.handle.net/10292/466

### Unpublished thesis (hardcopy) — `thesis_unpublished`

Pattern: `{author} ({year}). *{title}* (Unpublished {degree}). {institution}, {location}.`

Source: `theses` › Theses and dissertations in hardcopy format

- Example: Knight, A. (2001). *Exercise and osteoarthritis of the knee* (Unpublished master's dissertation). Auckland University of Technology, Auckland, New Zealand.

### Conference paper found online (incl. abstracts) — `conference_paper_online`

Pattern: `{author} ({year}, {month}). *{title}*. Paper presented at {meeting}, {location}. {retrieved_from|abstract_retrieved_from}`

Source: `conferences` › Conference papers found online; Conference paper - abstract retrieved online

- Example: Markman, K. M. (2003, October). *Taking the flesh with me: Embodied interaction as a framework for studying Internet communication*. Paper presented at the meeting of the Association of Internet Researchers, Toronto, Canada. Retrieved from https://umdrive.memphis.edu/kmmrkman/www/KMarkmanAOIR4Paper.pdf

### Conference paper, not formally published — `conference_paper_unpublished`

Pattern: `{author} ({year}, {month}). *{title}*. Paper presented at the meeting of {organisation}, {location}.`

Source: `conferences` › Paper presented in a conference

- Note: Include the year and month of the meeting.
- Example: (none in the guide)

### Symposium contribution — `symposium_contribution`

Pattern: `{author} ({year}, {month}). {title}. In {chair} (Chair), *{symposium_title}*. Symposium conducted at the meeting of {organisation}, {location}.`

Source: `conferences` › Symposium contribution

- Example: Muellbauer, J. (2007, September). Housing, credit, and consumer expenditure. In S. C. Ludvigson (Chair), *Housing and consumer behaviour*. Symposium conducted at the meeting of the Federal Reserve Bank of Kansas City, Jackson Hole, WY.

### Computer software, code or mobile app — `software`

Pattern: `{author} ({year}). {title}[ (Version {version})] [{software_type}].[ {location}: {publisher}.][ Retrieved from {url}]`

Source: `software` › Computer software and code; Mobile apps

- Note: Software title is not italic. Standard software (Word, SPSS, SAS, Java, Photoshop) need not be cited.
- Example: Esolang, A. N. (2014). Obscure Reference Generator [Computer software]. Washington, DC: E & K Press.
- Example: Skyscape. (2013). Skyscape Medical Resources (Version 1.17.42) [Mobile application software].

### Computer software, no rightsholder — `software_no_author`

Pattern: `{title} [{software_type}]. ({year}). Retrieved from {url}`

Source: `software` › Computer software and code

- Example: Customized Synergy [Computer software]. (2014). Retrieved from http://customizedsynergy.com

### Manual or handbook — `manual`

Pattern: `{corporate_author}. ({year}). *{title}*. {location}: {publisher}.`
Alternative: `{corporate_author}. ({year}). *{title}*. Retrieved from {url}`

Source: `software` › Manuals and handbooks

- Example: Honeywell. (2000). *MetroSelect® single-line scanner: Configuration guide*. Fort Mill, SC: Author.

### Film — `film`

Pattern: `{contributors}. ({year}). *{title}* [Motion picture]. {country}: {studio}.`

Source: `tvfilmvideo` › Film / Movie

- Example: Scorsese, M. (Producer), & Lonergan, K. (Writer/Director). (2000). *You can count on me* [Motion picture]. United States: Paramount Pictures.

### Television series — `tv_series`

Pattern: `{contributors}. ({year}). *{title}* [Television series]. {country}: {studio}.`

Source: `tvfilmvideo` › Television series

- Example: Laing, J. (Producer). (2006). *Outrageous fortune* [Television series]. New Zealand: South Pacific Pictures.

### Single episode of a television series — `tv_episode`

Pattern: `{contributors}. ({year}). {title} [Television series episode]. In {series_producer} (Executive producer), *{series_title}*. {location}: {studio}.`

Source: `tvfilmvideo` › Single episode in a television series

- Example: Egan, D. (Writer), & Alexander, J. (Director). (2005). Failure to communicate [Television series episode]. In D. Shore (Executive producer), *House*. New York, NY: Fox Broadcasting.

### Online video (YouTube etc.), podcast, streaming video, DVD — `online_video`

Pattern: `{author}[ [{screen_name}]]. ({year}, {month} {day}). *{title}* [{description}]. {retrieved_from|available_from}`

Source: `tvfilmvideo` › Video & DVD; Social media: Video podcasts / Audio podcast

- Note: Exact date of the post; no retrieval date.
- Note: A video that is part of a series of blog posts: title NOT italic (see online_video_series).
- Example: Bellofolletti. (2009, April 8). *Ghost caught on surveillance camera* [Video file]. Retrieved from http://www.youtube.com/watch?v=Dq1ms2JhYBI&feature=related
- Example: Dunning, B. [volleybrian]. (2011, January 12). *inFact: Conspiracy theories* [Video file]. Retrieved from http://www.youtube.com/watch?v=AEijdTeBMRM&index=5&feature=plcp
- Example: Van Nuys, D. (Producer). (2007, April 7). *The anatomy of a lobotomist* [Audio podcast]. Retrieved from http://www.shrinkrapradio.com/2007/04/07/84-anatomy-lobotomist

### Online video that is part of a series of blog posts — `online_video_series`

Pattern: `{author} ({year}, {month} {day}). {title} [Video file]. Retrieved from {url}`

Source: `tvfilmvideo` › YouTube video blog post

- Example: Norton, R. (2006, November 4). How to train a cat to operate a light switch [Video file]. Retrieved from http://www.youtube.com/w?v=IkMOd9PVuKg

### Blog post — `blog_post`

Pattern: `{author} ({year}, {month} {day}). {title} [Blog post]. Retrieved from {url}`

Source: `blogs` › Blogs

- Note: Post title not italic.
- Example: Hirst, M. (2009, April 3). Public television for $1 a day [Blog post]. Retrieved from http://ethicalmartini.wordpress.com/2009/04/03/public-television-for-1-a-day/

### Standard — `standard`

Pattern: `{corporate_author}. ({year}). *{title}* ({standard_number}). {retrieved_from|location_publisher}`

Source: `standards` › Standards

- Note: Joint standard: use the first organisation.
- Example: Standards Australia. (2009). *Risk management: Principles and guidelines* (AS/NZS ISO 31000:2009). Homebush, NSW: Standards Australia.
- Example: Standards New Zealand. (2013). *Conditions of contract for building and civil engineering construction* (NZS 3910:2013). Retrieved from https://shop-standards-govt-nz

### Patent — `patent`

Pattern: `{author} ({year}). *{patent_identifier}*. {location}: {source_name}.`

Source: `standards` › Patents

- Note: No patent title; date the patent was issued.
- Example: Fry, A. L. (1993). *U.S. Patent No. 5,194,299*. Washington, DC: U.S. Patent and Trademark Office.

### Cited in the text only (never in the reference list)

- Personal communication (emails, letters, interviews, conversations, own lecture notes): (I. Tokugawa, personal communication, January 25, 2019)
- An entire website: (http://www.kidspsyche.org)
- Facebook or Twitter feed

## 4. Guide examples with mistakes (spec §6.9)

| Page | Example | Problem | Action |
|---|---|---|---|
| `referencelist` | Kasabov et al. (2016) | no space before the journal name ('applications.*Neural Networks') | excluded |
| `articles` | Kasabov (2015b) | DOI prefix doubled (https://doi.org/https://doi.org/…); no publisher location (ruling 6.4); chapter title in title case; its in-text example cites 'Rush, 2015a' | excluded |
| `books` | Austen (1853) | full stop after the URL | excluded |
| `websites` | Harrison (2009) PowerPoint | no space in 'website:https://…' | excluded |
| `tvfilmvideo` | Dunning [volleybrian] (2011) | space inside the URL ('index =5') | corrected in templates: space removed |
| `books` | Esposito & Jain (2016) | no comma before '&' | excluded |
| `books` | Chong & Werner (2016) | no comma before '&'; '(Ed.)' for two editors; title not italic; no space before '[Custom textbook]' | excluded |
| `conferences` | Herculano-Houzel et al. (2008) | no comma before '&'; volume not italic | excluded |
| `referencelist` | Coltheart et al. (1993) | comma missing after 'Curtis, B.'; volume not italic | excluded |
| `referencelist` | Szczęsna et al. (2017) | first author's name garbled ('Szcz Ę Sna'); volume treated as title text | excluded |
| `conferences` | Porter, Omar, Campus, & Edinburgh (2008) | 'Campus, C.' and 'Edinburgh, S.' are parts of an institution name, not authors | excluded |
| `referencelist` | Rush et al. (2015b) | journal 'Annals Of Human Biology' capitalises the preposition 'Of' | excluded |
| `referencelist` | Barnard, de Luca, & Li (2015) | journal 'Studies In Higher Education' capitalises the preposition 'In' | excluded |
| `books` | Knox & Mayer (2009) | subtitle after the colon starts lowercase ('economic') | excluded |
| `software` | Skyscape (2013) | title typo 'Skyscap' | corrected in templates: Skyscape |
| `books` | Helmig & Thaler (2010) | no space in '(pp.151–169)' | corrected in templates: (pp. 151–169) |
| `books` | Gladwell (2008) | no space before '[Kindle DX version]' | corrected in templates: space added |
| `tvfilmvideo` | Egan & Alexander (2005) | semicolon after the series title '*House*;' | corrected in templates: full stop |
| `theses` | Pflieger (2009) | only part of the title is italic | corrected in templates: whole title italic |
| `conferences` | Markman (2003) | stray semicolon in the title ('Embodied; interaction') | corrected in templates: semicolon removed |
| `conferences` | Bruner (2000) | italics misplaced (starts on the article-title full stop) | excluded |
| `brief-guide-pdf` | (Gazda et al.,205) | wrong year (2005) and no space after the comma | excluded |
| `brief-guide-pdf` | (Bellofolleti, 2009) | spelling differs from the reference (Bellofolletti) | excluded |
| `articles` | (Wilson, Spies-Butcher & Stebbing, 2009) | no comma before '&' (compare the guide's '(Alred, Brusaw, & Oliu, 2009)') | excluded |
| `articles` | Liu and Seale (2007) / (Liu & Searl, 2007) | names do not match the reference Li & Seale (2007) | excluded |
| `articles` | (Rush, 2015a) under Kasabov (2015a) | name does not match the reference | excluded |
| `books` | (Gamble, 2009) | name does not match the reference Gambles (2009) | excluded |
| `books` | Alfred et al. (2009) | name does not match the reference Alred et al. (2009) | excluded |
| `books` | ("Nuke Test Inquiry,"2009) | no space before the year | excluded |
| `articles` | ("Nuke Test Inquiry" 2009) | no comma before the year | excluded |
| `intextcitation` | (Allen, 2004; Smith 1999; Tsvetkova, 2018 ) | no comma after 'Smith'; space before the closing bracket | excluded |
| `intextcitation` | (Pierre Janet,1906) | no space after the comma | excluded |
