import sublime, sublime_plugin
import re, string, os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), 'verilogutil'))
import verilogutil
import sublimeutil

class VerilogAlign(sublime_plugin.TextCommand):

    def run(self,edit):
        if len(self.view.sel())!=1 : return; # No multi-selection allowed (yet?)
        # Expand the selection to a complete scope supported by the one of the align function
        # Get sublime setting
        self.settings = self.view.settings()
        self.tab_size = int(self.settings.get('tab_size', 4))
        self.char_space = ' ' * self.tab_size
        self.use_space = self.settings.get('translate_tabs_to_spaces')
        current_pos = self.view.viewport_position()
        if not self.use_space:
            self.char_space = '\t'
        region = self.view.extract_scope(self.view.line(self.view.sel()[0]).a)
        scope = self.view.scope_name(region.a)
        txt = ''
        if 'meta.module.inst' in scope:
            (txt,region) = self.inst_align(region)
        elif 'meta.module.systemverilog' in scope:
            (txt,region) = self.port_align(region)
        else :
            region = self.view.line(self.view.sel()[0])
            if self.view.classify(region.b) & sublime.CLASS_EMPTY_LINE :
                region.b -= 1;
            txt = self.view.substr(region)
            # print('Before decl_align txt = ' + txt)
            (txt,region) = self.decl_align(txt, region)
            # print('Before assign_align txt = ' + txt)
            (txt,region) = self.assign_align(txt, region)
        if txt != '':
            self.view.replace(edit,region,txt)
            sublimeutil.move_cursor(self.view,region)
        else :
            sublime.status_message('No alignement support for this block of code.')

    def get_indent_level(self,txt):
        # make sure to not have mixed tab/space
        if self.use_space:
            t = txt.replace('\t',self.char_space)
        else:
            t = txt.replace(self.char_space,'\t')
        cnt = (len(t) - len(t.lstrip()))
        if self.use_space:
            cnt = int(cnt/self.tab_size)
        return cnt

    # Alignement for module instance
    def inst_align(self,region):
        r = sublimeutil.expand_to_scope(self.view,'meta.module.inst',region)
        # Make sure to get complete line to be able to get initial indentation
        r = self.view.line(r)
        txt = self.view.substr(r).rstrip()
        # Check if parameterized module
        m = re.search(r'(?s)(?P<mtype>^[ \t]*\w+)\s*(?P<paramsfull>#\s*\((?P<params>.*)\s*\))?\s*(?P<mname>\w+)\s*\(\s*(?P<ports>.*)\s*\)\s*;(?P<comment>.*)$',txt,re.MULTILINE)
        if not m:
            print('Unable to match a module instance !')
            return
        nb_indent = self.get_indent_level(m.group('mtype'))
        # Add module type
        txt_new = self.char_space*(nb_indent) + m.group('mtype').strip()
        #Add parameter binding : if already on one line simply remove extra space, otherwise apply standard alignement
        if m.group('params'):
            txt_new += ' #('
            if '\n' in m.group('params').strip() :
                txt_new += '\n'+self.inst_align_binding(m.group('params'),nb_indent+1)+self.char_space*(nb_indent)
            else :
                p = m.group('params').strip()
                p = re.sub(r'\s+','',p)
                p = re.sub(r'\),',r'), ',p)
                txt_new += p
            txt_new += ')'
        # Add module name
        txt_new += ' ' + m.group('mname') + ' ('
        # Add ports binding
        if m.group('ports'):
            # if port binding starts with a .* let it on the same line
            if not m.group('ports').startswith('.*'):
                txt_new += '\n'
            txt_new += self.inst_align_binding(m.group('ports'),nb_indent+1)
        # Add end
        txt_new += self.char_space*(nb_indent) + '); '
        if m.group('comment'):
            txt_new += m.group('comment')
        return (txt_new,r)

    def inst_align_binding(self,txt,nb_indent):
        was_split = False
        # insert line if needed to get one binding per line
        if self.settings.get('sv.one_bind_per_line',True):
            txt = re.sub(r'\)[ \t]*,[ \t]*\.', '), \n.', txt,re.MULTILINE)
        # Parse bindings to find length of port and signals
        re_str_bind_port = r'\.\s*(?P<port>\w+)\s*\(\s*'
        re_str_bind_sig = r'(?P<signal>.*)\s*\)\s*(?P<comma>,)?\s*(?P<comment>\/\/.*?|\/\*.*?)?$'
        binds = re.findall(re_str_bind_port+re_str_bind_sig,txt,re.MULTILINE)
        max_port_len = 0
        max_sig_len = 0
        ports_len = [len(x[0]) for x in binds]
        sigs_len = [len(x[1].strip()) for x in binds]
        if ports_len:
            max_port_len = max(ports_len)
        if sigs_len:
            max_sig_len = max(sigs_len)
        #TODO: if the .* is at the beginning make sure it is not follow by another binding
        lines = txt.splitlines()
        txt_new = ''
        # for each line apply alignment
        for i,line in enumerate(lines):
            # Remove leading and trailing space. add end of line
            l = line.strip()
            # ignore empty line at the begining and the end of the connection
            if (i!=(len(lines)-1) and i!=0) or l !='':
                # Look for a binding
                m = re.search(r'^'+re_str_bind_port+re_str_bind_sig,l)
                is_split = False
                # No complete binding : look for just the beginning then
                if not m:
                    m = re.search(re_str_bind_port+r'(?P<signal>.*?)\s*(?P<comma>)(?P<comment>)$',l)
                    is_split = True
                    # print('Detected split at Line ' + str(i) + ' : ' + l)
                if m:
                    # print('Line ' + str(i) + ' : ' + str(m.groups()) + ' => split = ' + str(is_split))
                    txt_new += self.char_space*(nb_indent)
                    txt_new += '.' + m.group('port').ljust(max_port_len)
                    txt_new += '(' + m.group('signal').strip().ljust(max_sig_len)
                    if not is_split:
                        txt_new += ')'
                        if m.group('comma'):
                            txt_new += ', '
                        else:
                            txt_new += '  '
                    if m.group('comment'):
                        txt_new += m.group('comment')
                else : # No port binding ? recopy line with just the basic indentation level
                    txt_new += self.char_space*nb_indent
                    # Handle case of binding split on multiple line : try to align the end of the binding
                    if was_split:
                        txt_new += ''.ljust(max_port_len+2) #2 = take into account the . and the (
                        m = re.search(re_str_bind_sig,l)
                        if m:
                            if m.group('signal'):
                                txt_new += m.group('signal').strip().ljust(max_sig_len) + ')'
                            else :
                                txt_new += ''.strip().ljust(max_sig_len) + ')'
                            if m.group('comma'):
                                txt_new += ', '
                            else:
                                txt_new += '  '
                            if m.group('comment'):
                                txt_new += m.group('comment')
                        else :
                            txt_new += l
                    else :
                        txt_new += l
                was_split = is_split
                txt_new += '\n'
        return txt_new

    # Alignement for port declaration (for ansi-style)
    def port_align(self,region):
        r = sublimeutil.expand_to_scope(self.view,'meta.module.systemverilog',region)
        r = self.view.expand_by_class(r,sublime.CLASS_LINE_START | sublime.CLASS_LINE_END)
        txt = self.view.substr(r)
        # print('Port alignement on :' + txt)
        #TODO: handle interface
        # Port declaration: direction type? signess? buswidth? portlist ,? comment?
        re_str = r'^[ \t]*(?P<dir>[\w\.]+)[ \t]+(?P<var>var\b)?[ \t]*(?P<type>[\w\:]+\b)?[ \t]*(?P<sign>signed|unsigned\b)?[ \t]*(\[(?P<bw>[\w\:\-` \t]+)\])?[ \t]*(?P<portlist>\w+[\w, \t]*)(?P<ending>\)\s+;)?[ \t]*(?P<comment>.*)'
        decl = re.findall(re_str,txt,re.MULTILINE)
        # if decl:
        #     print(decl)
        # Extract max length of the different field for vertical alignement
        len_dir  = max([len(x[0]) for x in decl if x[0]!='module'])
        len_var  = max([len(x[1]) for x in decl if x[0]!='module'])
        len_bw   = max([len(re.sub(r'\s*','',x[5])) for x in decl if x[0]!='module'])
        max_port_len = max([len(re.sub(r',',', ',re.sub(r'\s*','',x[6])))-2 for x in decl if x[0]!='module'])
        len_sign = 0
        len_type = 0
        len_type_user = 0
        for x in decl:
            if x[0]!='module':
                if x[1] == '' and x[3]=='' and x[4]=='' and x[2] not in ['logic', 'wire', 'reg', 'signed', 'unsigned']:
                    if len_type_user < len(x[2]) :
                        len_type_user = len(x[2])
                else :
                    if len_type < len(x[2]) and  x[2] not in ['signed','unsigned']:
                        len_type = len(x[2])
                if x[2] in ['signed','unsigned'] and len_sign<len(x[2]):
                    len_sign = len(x[2])
                elif x[3] in ['signed','unsigned'] and len_sign<len(x[3]):
                    len_sign = len(x[3])
        len_type_full = len_type
        if len_var > 0 or len_bw > 0 or len_sign > 0 :
            len_type_full +=1
            if len_var > 0:
                len_type_full += 4
            if len_bw > 0:
                len_type_full += 3+len_bw
            if len_sign > 0:
                len_type_full += 1+len_sign
        if len_type_user < len_type_full:
            len_type_user = len_type_full
        # print('Len:  dir=' + str(len_dir) + ' type=' + str(len_type) + ' sign=' + str(len_sign) + ' bw=' + str(len_bw) + ' type_user=' + str(len_type_user) + ' port=' + str(max_port_len))
        # Rewrite block line by line with padding for alignment
        txt_new = ''
        lines = txt.splitlines()
        nb_indent = self.get_indent_level(lines[0])
        for i,line in enumerate(lines):
            # Remove leading and trailing space. add end of line
            l = line.strip()
            #Special case of first line: potentially insert an end of line between instance name and port name
            if i==0 or (i==1 and lines[0]==''):
                txt_new += self.char_space*nb_indent+l + '\n'
            else :
                if i == len(lines)-1:
                    txt_new += self.char_space*(nb_indent)
                else:
                    txt_new += self.char_space*(nb_indent+1)
                m = re.search(re_str,l)
                if m:
                    # print('Line ' + str(i) + ' : ' + str(m.groups()))
                    # Add direction
                    txt_new += m.group('dir').ljust(len_dir)
                    # Align userdefined type differently from the standard type
                    if m.group('var') or m.group('sign') or m.group('bw') or m.group('type') in ['logic', 'wire', 'reg', 'signed', 'unsigned']:
                        if len_var>0:
                            if m.group('var'):
                                txt_new += ' ' + m.group('var')
                            else:
                                txt_new += ' '.ljust(len_var+1)
                        if len_type>0:
                            if m.group('type'):
                                if m.group('type') not in ['signed','unsigned']:
                                    txt_new += ' ' + m.group('type').ljust(len_type)
                                else:
                                    txt_new += ''.ljust(len_type+1) + ' ' + m.group('type').ljust(len_sign)
                            else:
                                txt_new += ''.ljust(len_type+1)
                            # add sign space it exists at least for one port
                            if len_sign>0:
                                if m.group('sign'):
                                    txt_new += ' ' + m.group('sign').ljust(len_sign)
                                elif m.group('type') not in ['signed','unsigned']:
                                    txt_new += ''.ljust(len_sign+1)
                        elif len_sign>0:
                            if m.group('type') in ['signed','unsigned']:
                                txt_new += ' ' + m.group('type').ljust(len_sign)
                            elif m.group('sign'):
                                txt_new += ' ' + m.group('sign').ljust(len_sign)
                            else:
                                txt_new += ''.ljust(len_sign+1)
                        # Add bus width if it exists at least for one port
                        if len_bw>1:
                            if m.group('bw'):
                                txt_new += ' [' + m.group('bw').strip().rjust(len_bw) + ']'
                            else:
                                txt_new += ''.rjust(len_bw+3)
                        if len_type_user > len_type_full:
                            txt_new += ''.ljust(len_type_user-len_type_full)
                    elif m.group('type') :
                        txt_new += ' ' + m.group('type').ljust(len_type_user)
                    else :
                        txt_new += ' '.ljust(len_type_user)
                    # Add port list: space every port in the list by just on space
                    s = re.sub(r',',', ',re.sub(r'\s*','',m.group('portlist')))
                    txt_new += ' '
                    if s.endswith(', '):
                        txt_new += s[:-2].ljust(max_port_len) + ','
                    else:
                        txt_new += s.ljust(max_port_len) + ' '
                    # If declaration finish with ); insert an eol
                    if m.group('ending') :
                        txt_new += '\n' + self.char_space*nb_indent + ');'
                    # Add comment
                    if m.group('comment') :
                        txt_new += ' ' + m.group('comment')
                else : # No port declaration ? recopy line with just the basic indentation level
                    txt_new += l
                # Remove trailing spaces/tabs and add the end of line
                txt_new = txt_new.rstrip(' \t') + '\n'

        return (txt_new,r)


    # Alignement for signal declaration : [scope::]type [signed|unsigned] [bitwidth] signal list
    def decl_align(self,txt, region):
        lines = txt.splitlines()
        #TODO handle array
        re_str = r'^[ \t]*(\w+\:\:)?(\w+)[ \t]+(signed|unsigned\b)?[ \t]*(\[([\w\:\-` \t]+)\])?[ \t]*([\w\[\]]+)[ \t]*(,[\w, \t]*)?;[ \t]*(.*)'
        lines_match = []
        len_max = [0,0,0,0,0,0,0,0]
        nb_indent = -1
        one_decl_per_line = self.settings.get('sv.one_decl_per_line',False)
        # Process each line to identify a signal declaration, save the match information in an array, and process the max length for each field
        for l in lines:
            m = re.search(re_str,l)
            lines_match.append(m)
            if m:
                if nb_indent < 0:
                    nb_indent = self.get_indent_level(l)
                for i,g in enumerate(m.groups()):
                    if g:
                        if len(g.strip()) > len_max[i]:
                            len_max[i] = len(g.strip())
                        if i==6 and one_decl_per_line:
                            for s in g.split(','):
                                if len(s.strip()) > len_max[5]:
                                    len_max[5] = len(s.strip())
        # Update alignement of each line
        txt_new = ''
        for line,m in zip(lines,lines_match):
            if m:
                l = self.char_space*nb_indent
                if m.groups()[0]:
                    l += m.groups()[0]
                l += m.groups()[1].ljust(len_max[0]+len_max[1]+1)
                #Align with signess only if it exist in at least one of the line
                if len_max[2]>0:
                    if m.groups()[2]:
                        l += m.groups()[2].ljust(len_max[2]+1)
                    else:
                        l += ''.ljust(len_max[2]+1)
                #Align with signess only if it exist in at least one of the line
                if len_max[4]>1:
                    if m.groups()[4]:
                        l += '[' + m.groups()[4].strip().rjust(len_max[4]) + '] '
                    else:
                        l += ''.rjust(len_max[4]+3)
                d = l # save signal declaration before signal name in case it needs to be repeated for a signal list
                # list of signals : do not align with the end of lign
                if m.groups()[6]:
                    l += m.groups()[5]
                    if one_decl_per_line:
                        for s in m.groups()[6].split(','):
                            if s != '':
                                l += ';\n' + d + s.strip().ljust(len_max[5])
                    else :
                        l += m.groups()[6].strip()
                else :
                    l += m.groups()[5].ljust(len_max[5])
                l += ';'
                if m.groups()[7]:
                    l += ' ' + m.groups()[7].strip()
            else : # Not a declaration ? don't touch
                l = line
            txt_new += l + '\n'
        return (txt_new[:-1],region)

    # Alignement for case/structure assign : "word: statement"
    def assign_align(self,txt, region):
        #TODO handle array
        re_str_l = []
        re_str_l.append(r'^[ \t]*(?P<scope>\w+\:\:)?(?P<name>[\w`\'\"\.]+)[ \t]*(\[(?P<bitslice>.*?)\])?\s*(?P<op>\:)\s*(?P<statement>.*)$')
        re_str_l.append(r'^[ \t]*(?P<scope>assign)\s+(?P<name>[\w`\'\"\.]+)[ \t]*(\[(?P<bitslice>.*?)\])?\s*(?P<op>=)\s*(?P<statement>.*)$')
        re_str_l.append(r'^[ \t]*(?P<scope>)(?P<name>[\w`\'\"\.]+)[ \t]*(\[(?P<bitslice>.*?)\])?\s*(?P<op>(<)?=)\s*(?P<statement>.*)$')
        txt_new = txt
        for re_str in re_str_l:
            lines = txt_new.splitlines()
            lines_match = []
            nb_indent = -1
            max_len = 0
            # Process each line to identify a signal declaration, save the match information in an array, and process the max length for each field
            for l in lines:
                m = re.search(re_str,l)
                lines_match.append(m)
                if m:
                    if nb_indent < 0:
                        nb_indent = self.get_indent_level(l)
                    len_c = len(m.group('name'))
                    if m.group('scope'):
                        len_c += len(m.group('scope'))
                        if m.group('scope') == 'assign':
                            len_c+=1
                    if m.group('bitslice'):
                        len_c += len(re.sub(r'\s','',m.group('bitslice')))+2
                    if len_c > max_len:
                        max_len = len_c
            # If no match return text as is
            if max_len!=0 :
                txt_new = ''
                # Update alignement of each line
                for line,m in zip(lines,lines_match):
                    if m:
                        l = ''
                        if m.group('scope'):
                            l += m.group('scope')
                            if m.group('scope') == 'assign':
                                l+=' '
                        l += m.group('name')
                        if m.group('bitslice'):
                            l += '[' + re.sub(r'\s','',m.group('bitslice')) + ']'
                        l = self.char_space*nb_indent + l.ljust(max_len) + ' ' + m.group('op') + ' ' + m.group('statement')
                    else :
                        l = line
                    txt_new += l + '\n'
                txt_new = txt_new[:-1]

        return (txt_new,region)

